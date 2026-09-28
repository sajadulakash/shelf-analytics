"""Postgres access for the Database Data Dump pipeline.

Thin, synchronous psycopg2 layer. Two kinds of helper live here:

* **Worker helpers** take an explicit ``conn`` — the data-dump consumer owns one
  connection and drives it serially from a worker thread via
  ``asyncio.to_thread``.
* **One-shot helpers** open (and close) their own connection. They are used by
  request handlers and at startup, where no long-lived connection exists.

A dump job and its per-image progress are stored here too, so a job survives a
reload, a crash, or a power cut and can be resumed exactly where it stopped.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

from app import config

# One row per detected + classified product.
_INSERT_SQL = (
    "INSERT INTO product_detections "
    "(image_id, class_name, x_center, y_center, bbox_width, bbox_height) VALUES %s"
)

DetectionRow = tuple[str, str, float, float, float, float]

# Job/item bookkeeping. ``product_detections`` is created here too so a fresh
# database works out of the box; on an existing one these are all no-ops.
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS product_detections (
    image_id    TEXT,
    class_name  TEXT,
    x_center    DOUBLE PRECISION,
    y_center    DOUBLE PRECISION,
    bbox_width  DOUBLE PRECISION,
    bbox_height DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS data_dump_jobs (
    job_id          TEXT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    status          TEXT NOT NULL,
    total_images    INTEGER NOT NULL,
    error           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS data_dump_items (
    job_id       TEXT NOT NULL REFERENCES data_dump_jobs(job_id) ON DELETE CASCADE,
    image_id     TEXT NOT NULL,
    image_url    TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    reason       TEXT,
    rows_written INTEGER NOT NULL DEFAULT 0,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, image_id)
);

CREATE INDEX IF NOT EXISTS data_dump_items_job_status_idx
    ON data_dump_items (job_id, status);
"""

# A job in one of these states has work left that a resume can pick up.
RESUMABLE_STATUSES = ("interrupted", "failed", "canceled")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def connect(autocommit: bool = False):
    """Open a new Postgres connection using the configured credentials."""
    conn = psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    conn.autocommit = autocommit
    return conn


def ping() -> None:
    """Raise if the database is unreachable (fail fast before a run starts)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    finally:
        conn.close()


def ensure_schema() -> None:
    """Create the dump tables if they are not there yet."""
    conn = connect(autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
    finally:
        conn.close()


# ---------- Job lifecycle ----------
def create_job(job_id: str, source_filename: str, rows: list[tuple[str, str]]) -> int:
    """Persist a new job and all its CSV rows in one transaction.

    This is what makes a dump survive a restart: the work queue is on disk
    *before* the caller is told the job started. Returns the number of items
    stored (duplicate ``image_id``s in the CSV collapse into one).
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO data_dump_jobs (job_id, source_filename, status, total_images) "
                "VALUES (%s, %s, 'queued', %s)",
                (job_id, source_filename, len(rows)),
            )
            execute_values(
                cur,
                "INSERT INTO data_dump_items (job_id, image_id, image_url) VALUES %s "
                "ON CONFLICT (job_id, image_id) DO NOTHING",
                [(job_id, image_id, url) for image_id, url in rows],
            )
            cur.execute("SELECT count(*) FROM data_dump_items WHERE job_id = %s", (job_id,))
            stored = int(cur.fetchone()[0])
            cur.execute(
                "UPDATE data_dump_jobs SET total_images = %s WHERE job_id = %s",
                (stored, job_id),
            )
        conn.commit()
        return stored
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_job_status(
    conn,
    job_id: str,
    status: str,
    *,
    error: str | None = None,
    started: bool = False,
    finished: bool = False,
) -> None:
    """Update a job's status (and optionally stamp start/finish)."""
    sets = ["status = %s", "error = %s"]
    params: list[Any] = [status, error]
    if started:
        sets.append("started_at = coalesce(started_at, %s)")
        params.append(_now())
    if finished:
        sets.append("finished_at = %s")
        params.append(_now())
    params.append(job_id)
    with conn.cursor() as cur:
        cur.execute(f"UPDATE data_dump_jobs SET {', '.join(sets)} WHERE job_id = %s", params)
    if not conn.autocommit:
        conn.commit()


def load_job(job_id: str) -> dict | None:
    """Read one job row plus its aggregated progress."""
    conn = connect(autocommit=True)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM data_dump_jobs WHERE job_id = %s", (job_id,))
            job = cur.fetchone()
            if not job:
                return None
            return {**dict(job), **_counts(cur, job_id)}
    finally:
        conn.close()


def list_jobs(limit: int = 25) -> list[dict]:
    """Recent jobs, newest first, each with its aggregated progress."""
    conn = connect(autocommit=True)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM data_dump_jobs ORDER BY created_at DESC LIMIT %s", (limit,)
            )
            jobs = [dict(row) for row in cur.fetchall()]
            return [{**job, **_counts(cur, job["job_id"])} for job in jobs]
    finally:
        conn.close()


def _counts(cur, job_id: str) -> dict:
    """Aggregate per-item progress for a job (done / failed / pending / rows)."""
    cur.execute(
        "SELECT status, count(*) AS n, coalesce(sum(rows_written), 0) AS written "
        "FROM data_dump_items WHERE job_id = %s GROUP BY status",
        (job_id,),
    )
    processed = failed = pending = written = 0
    for row in cur.fetchall():
        status, n, w = row["status"], int(row["n"]), int(row["written"])
        if status == "done":
            processed, written = n, w
        elif status == "failed":
            failed = n
        else:
            pending += n
    return {
        "processed_images": processed,
        "failed_images": failed,
        "pending_images": pending,
        "rows_written": written,
    }


def recent_failures(job_id: str, limit: int) -> list[dict]:
    """The first ``limit`` failed items of a job, for the status payload."""
    conn = connect(autocommit=True)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT image_id, image_url, reason FROM data_dump_items "
                "WHERE job_id = %s AND status = 'failed' ORDER BY updated_at LIMIT %s",
                (job_id, limit),
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def reconcile_interrupted_jobs() -> list[str]:
    """Flag jobs left mid-flight by a crash/restart and return their ids.

    Nothing can be running right after the process starts, so any job still
    marked ``queued``/``running`` was cut off and is safe to reopen.
    """
    conn = connect(autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE data_dump_jobs SET status = 'interrupted' "
                "WHERE status IN ('queued', 'running') RETURNING job_id"
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


# ---------- Item queue ----------
def pending_items(conn, job_id: str) -> list[tuple[str, str]]:
    """Rows of a job that still need processing, as ``(image_id, image_url)``."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT image_id, image_url FROM data_dump_items "
            "WHERE job_id = %s AND status = 'pending' ORDER BY image_id",
            (job_id,),
        )
        return [(row[0], row[1]) for row in cur.fetchall()]


def mark_item_failed(conn, job_id: str, image_id: str, reason: str) -> None:
    """Record a per-image failure so a resume does not retry it forever."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE data_dump_items SET status = 'failed', reason = %s, updated_at = now() "
            "WHERE job_id = %s AND image_id = %s",
            (reason[:500], job_id, image_id),
        )
    if not conn.autocommit:
        conn.commit()


def complete_item(conn, job_id: str, image_id: str, rows: Iterable[DetectionRow]) -> int:
    """Insert an image's detections **and** mark it done, atomically.

    Both writes share one transaction, so a crash can never leave detections in
    the database with the item still pending — which on resume would reprocess
    the image and duplicate every row. Returns the number of detections written.
    """
    rows = list(rows)
    try:
        with conn.cursor() as cur:
            if rows:
                execute_values(cur, _INSERT_SQL, rows)
            cur.execute(
                "UPDATE data_dump_items SET status = 'done', rows_written = %s, "
                "updated_at = now() WHERE job_id = %s AND image_id = %s",
                (len(rows), job_id, image_id),
            )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
