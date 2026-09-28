"""Background sync of detections to the remote product-sense database.

Rows land in the local ``product_detections`` first; this worker then pushes
whatever is still unsynced to the remote ``market_intelligence_inference`` table
and stamps ``synced_at`` on what it sent. That column is the whole protocol:
NULL means "not sent yet", so a crash, a restart or a dropped connection costs
nothing but a repeat of the batch in flight.

**Column mapping.** The remote's ``x1/y1/x2/y2`` are misnamed -- they hold
centre-x, centre-y, width and height, normalised 0-1, exactly like the local
columns. Verified against 8.72M live rows: all but 34,522 are invalid read as
corner boxes, and not one is invalid read as centre+size, with
``min(x1)*2 == min(x2)`` exactly (a box touching the edge has centre = width/2).
So the copy is 1:1 and no geometry conversion happens here.

The worker is **off by default** and its state lives in ``data/sync_config.json``
so the toggle survives a restart.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import execute_values

from app import config, db

logger = logging.getLogger(__name__)

_INSERT_REMOTE = (
    "INSERT INTO {table} "
    "(id, image_id, class_label, x1, y1, x2, y2, model_id) VALUES %s"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- On/off state ----------
# Kept in the database, not a file: the API server and the sync worker are
# separate processes, so this is what they agree through.
SYNC_ENABLED_KEY = "sync_enabled"


def is_enabled() -> bool:
    try:
        return db.get_setting(SYNC_ENABLED_KEY, "false") == "true"
    except Exception:  # noqa: BLE001 - unreachable database means "not running"
        return False


def set_enabled(enabled: bool) -> bool:
    db.set_setting(SYNC_ENABLED_KEY, "true" if enabled else "false")
    logger.info("Sync %s", "enabled" if enabled else "disabled")
    return bool(enabled)


_RUNTIME: dict = {
    "running": False,
    "last_run_at": None,
    "last_error": None,
    "last_synced": 0,
    "total_synced": 0,
    "next_due": None,
}


def configured() -> bool:
    """A password is required, so the sync cannot run on defaults alone."""
    return bool(config.SYNC_DB_PASSWORD)


# ---------- Remote connection ----------
def _connect_remote():
    return psycopg2.connect(
        host=config.SYNC_DB_HOST,
        port=config.SYNC_DB_PORT,
        dbname=config.SYNC_DB_NAME,
        user=config.SYNC_DB_USER,
        password=config.SYNC_DB_PASSWORD,
        connect_timeout=config.SYNC_CONNECT_TIMEOUT,
    )


def ping_remote() -> None:
    """Raise if the remote is unreachable (read-only, writes nothing)."""
    conn = _connect_remote()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    finally:
        conn.close()


# ---------- One cycle (runs in a worker thread) ----------
def _sync_once() -> tuple[int, int]:
    """Push every pending row, in batches. Returns ``(rows_sent, batches)``."""
    local = db.connect()
    remote = _connect_remote()
    sql = _INSERT_REMOTE.format(table=config.SYNC_TABLE)
    sent = batches = 0
    try:
        while True:
            rows = db.unsynced_batch(local, config.SYNC_BATCH_SIZE)
            local.rollback()  # end the read transaction; nothing to keep open
            if not rows:
                break

            with remote.cursor() as cur:
                execute_values(cur, sql, rows)
            remote.commit()

            # Only after the remote has committed. If the process dies in this
            # gap the batch is re-sent next cycle -- duplicated rather than
            # lost, which is the safer direction. A unique index on the remote
            # id column would close that window entirely.
            db.mark_synced(local, [r[0] for r in rows])
            sent += len(rows)
            batches += 1
    finally:
        local.close()
        remote.close()
    return sent, batches


async def run_now() -> dict:
    """Run one full sync cycle and report what it did."""
    if not configured():
        raise RuntimeError("SYNC_DB_PASSWORD is not set; refusing to sync.")
    if _RUNTIME["running"]:
        return {"skipped": "already running"}

    _RUNTIME["running"] = True
    _RUNTIME["last_error"] = None
    try:
        sent, batches = await asyncio.to_thread(_sync_once)
        _RUNTIME["last_synced"] = sent
        _RUNTIME["total_synced"] += sent
        logger.info("Sync: pushed %d row(s) in %d batch(es)", sent, batches)
        return {"rows_synced": sent, "batches": batches}
    except Exception as e:  # noqa: BLE001
        _RUNTIME["last_error"] = str(e)
        logger.exception("Sync cycle failed")
        raise
    finally:
        _RUNTIME["running"] = False
        _RUNTIME["last_run_at"] = _now()


# ---------- Scheduler (run by sync_worker.py, not by the API) ----------
async def loop() -> None:
    """Wake often, sync rarely.

    The short poll is only so flipping the toggle takes effect in seconds; an
    actual cycle still runs once per SYNC_INTERVAL_SECONDS.
    """
    while True:
        try:
            await asyncio.sleep(config.SYNC_POLL_SECONDS)
            if not is_enabled() or not configured() or _RUNTIME["running"]:
                continue
            now = _now()
            due = _RUNTIME["next_due"]
            if due is not None and now < due:
                continue
            try:
                await run_now()
            except Exception:  # noqa: BLE001 - already logged; keep the loop alive
                pass
            _RUNTIME["next_due"] = _now() + timedelta(seconds=config.SYNC_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Sync loop error")


def status() -> dict:
    counts = db.sync_counts()
    return {
        "enabled": is_enabled(),
        "configured": configured(),
        "running": _RUNTIME["running"],
        "interval_seconds": config.SYNC_INTERVAL_SECONDS,
        "batch_size": config.SYNC_BATCH_SIZE,
        "destination": f"{config.SYNC_DB_NAME}.{config.SYNC_TABLE} @ {config.SYNC_DB_HOST}",
        "pending": counts["pending"],
        "blocked": counts["blocked"],
        "synced": counts["synced"],
        "last_run_at": _RUNTIME["last_run_at"].isoformat() if _RUNTIME["last_run_at"] else None,
        "last_synced": _RUNTIME["last_synced"],
        "total_synced": _RUNTIME["total_synced"],
        "last_error": _RUNTIME["last_error"],
        "next_due": _RUNTIME["next_due"].isoformat() if _RUNTIME["next_due"] else None,
    }
