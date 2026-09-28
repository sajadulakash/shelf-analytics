"""Database Data Dump pipeline.

CSV of ``(image_id, image_url)`` -> download each image -> detect (YOLO, optional
SAHI) -> classify (SwinV2) -> insert rows into the Postgres ``product_detections``
table. Images and crops live in memory only and are discarded after each image;
nothing is written to disk.

The run is a background job: downloads run concurrently and feed a bounded queue,
while a single GPU consumer processes one image at a time (classifying its crops
in batches). Callers start a job and poll its status.

**Durability.** The job and every CSV row are written to Postgres before the
upload request returns, and each image is marked done in the same transaction as
its detections. So a browser reload, a server restart or a power cut costs at
most the image that was in flight: on the next start, interrupted jobs are
reopened and (by default) resumed from the first row that never finished.
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

from app import config, db, model_config
from app import classifier, detection_service

logger = logging.getLogger(__name__)

_SENTINEL = object()

# Header aliases accepted in the uploaded CSV.
_ID_KEYS = ("image_id", "id", "imageid", "image")
_URL_KEYS = ("image_url", "url", "imageurl", "link")

TERMINAL_STATUSES = ("completed", "failed", "canceled", "interrupted")

# Magic-byte signatures — a cheap "is this actually an image?" check that avoids
# decoding a full 16 MP file just to validate. Corrupt-but-plausible files still
# get caught later at detection time.
_IMAGE_MAGIC = (
    b"\xff\xd8\xff",            # JPEG
    b"\x89PNG\r\n\x1a\n",       # PNG
    b"GIF87a", b"GIF89a",        # GIF
    b"BM",                        # BMP
    b"II*\x00", b"MM\x00*",      # TIFF
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _looks_like_image(data: bytes) -> bool:
    if len(data) < 12:
        return False
    if data[8:12] == b"WEBP":  # RIFF....WEBP
        return True
    return data.startswith(_IMAGE_MAGIC)


# ---------- Download error typing ----------
class _Transient(Exception):
    """Retryable (timeout, connection reset, 5xx)."""


class _Permanent(Exception):
    """Not retryable (404, non-image body)."""


# ---------- CSV ----------
def parse_csv(raw: bytes) -> tuple[list[tuple[str, str]], str | None]:
    """Return ``(rows, error)`` where rows are ``(image_id, image_url)``."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], "CSV is empty or has no header row."

    norm = {name: name.strip().casefold().replace(" ", "_") for name in reader.fieldnames}
    id_col = next((orig for orig, n in norm.items() if n in _ID_KEYS), None)
    url_col = next((orig for orig, n in norm.items() if n in _URL_KEYS), None)
    if not id_col or not url_col:
        return [], "CSV must have an image_id column and an image_url column."

    rows: list[tuple[str, str]] = []
    seen: set[str] = set()
    for record in reader:
        image_id = str(record.get(id_col, "") or "").strip()
        image_url = str(record.get(url_col, "") or "").strip()
        # image_id keys the work queue, so a repeat is the same unit of work.
        if image_id and image_url and image_id not in seen:
            seen.add(image_id)
            rows.append((image_id, image_url))
    if not rows:
        return [], "No valid (image_id, image_url) rows found."
    return rows, None


# ---------- Job model ----------
@dataclass
class DataDumpJob:
    """Live view of a job. Durable state is in Postgres; this mirrors it in
    memory while the job runs so polling stays cheap."""

    job_id: str
    source_filename: str
    total_images: int
    status: str = "queued"  # queued|running|completed|failed|canceled|interrupted
    processed_images: int = 0
    failed_images: int = 0
    skipped_images: int = 0
    rows_written: int = 0
    pending_images: int = 0
    config_key: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested: bool = False

    @classmethod
    def from_db(cls, row: dict) -> "DataDumpJob":
        return cls(
            job_id=row["job_id"],
            source_filename=row["source_filename"],
            total_images=row["total_images"],
            status=row["status"],
            processed_images=row["processed_images"],
            failed_images=row["failed_images"],
            skipped_images=row["skipped_images"],
            rows_written=row["rows_written"],
            pending_images=row["pending_images"],
            config_key=row.get("config_key"),
            error=row.get("error"),
            created_at=row["created_at"],
            started_at=row.get("started_at"),
            finished_at=row.get("finished_at"),
        )

    def record_failure(self) -> None:
        """Count a failed image. The per-image reason lives in data_dump_items,
        which is what resume and the Runtime feed read."""
        self.failed_images += 1

    @property
    def resumable(self) -> bool:
        return self.status in db.RESUMABLE_STATUSES and self.pending_images > 0

    def snapshot(self) -> dict:
        return {
            "job_id": self.job_id,
            "source_filename": self.source_filename,
            "status": self.status,
            "total_images": self.total_images,
            "processed_images": self.processed_images,
            "failed_images": self.failed_images,
            "skipped_images": self.skipped_images,
            "pending_images": self.pending_images,
            "rows_written": self.rows_written,
            "detections": self.rows_written,
            "resumable": self.resumable,
            "config_key": self.config_key,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# Jobs with a task running *in this process*. Everything else is read from
# Postgres, so a job stays visible across restarts.
_LIVE: dict[str, DataDumpJob] = {}
_TASKS: set[asyncio.Task] = set()


def get_job(job_id: str) -> DataDumpJob | None:
    live = _LIVE.get(job_id)
    if live:
        return live
    row = db.load_job(job_id)
    if not row:
        return None
    return DataDumpJob.from_db(row)


def list_jobs(limit: int = 25) -> list[DataDumpJob]:
    jobs: list[DataDumpJob] = []
    for row in db.list_jobs(limit):
        live = _LIVE.get(row["job_id"])
        jobs.append(live if live else DataDumpJob.from_db(row))
    return jobs


def request_cancel(job_id: str) -> bool:
    job = _LIVE.get(job_id)
    if not job or job.status not in ("queued", "running"):
        return False
    job.cancel_requested = True
    return True


async def start_job(source_filename: str, rows: list[tuple[str, str]]) -> DataDumpJob:
    """Persist the whole work queue, then start processing it.

    Async because the task has to be created on the event loop, while the
    (blocking) write of the work queue goes to a worker thread.
    """
    job_id = uuid.uuid4().hex[:12]
    config_key = await asyncio.to_thread(model_config.active_config_key)
    stored = await asyncio.to_thread(db.create_job, job_id, source_filename, rows, config_key)
    job = DataDumpJob(
        job_id=job_id,
        source_filename=source_filename,
        total_images=stored,
        pending_images=stored,
        config_key=config_key,
    )
    _spawn(job)
    return job


async def resume_job(job_id: str) -> DataDumpJob | None:
    """Pick an interrupted/canceled/failed job back up from its pending rows."""
    if job_id in _LIVE:
        return _LIVE[job_id]
    job = await asyncio.to_thread(get_job, job_id)
    if not job or not job.resumable:
        return None
    job.cancel_requested = False
    _spawn(job)
    return job


def _spawn(job: DataDumpJob) -> None:
    _LIVE[job.job_id] = job
    task = asyncio.create_task(_run(job))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def reconcile_on_startup() -> list[str]:
    """Reopen jobs cut off by a restart, and resume them unless disabled."""
    interrupted = await asyncio.to_thread(db.reconcile_interrupted_jobs)
    if not interrupted:
        return []
    logger.info("Data dump: %d interrupted job(s) found: %s", len(interrupted), interrupted)
    if not config.DATA_DUMP_AUTO_RESUME:
        return interrupted

    resumed = []
    for job_id in interrupted:
        if await resume_job(job_id):
            resumed.append(job_id)
            logger.info("Data dump %s: auto-resumed", job_id)
    return resumed


# ---------- Download ----------
async def _download_once(client: httpx.AsyncClient, url: str) -> bytes:
    try:
        resp = await client.get(url)
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise _Transient(type(e).__name__)

    code = resp.status_code
    if code == 200:
        data = resp.content
        if not data or not _looks_like_image(data):
            raise _Permanent("not_an_image")
        return data
    if code in (408, 429) or 500 <= code < 600:
        raise _Transient(f"http_{code}")
    raise _Permanent(f"http_{code}")


async def _download(client: httpx.AsyncClient, url: str, retries: int) -> bytes:
    attempt = 0
    while True:
        try:
            return await _download_once(client, url)
        except _Permanent:
            raise
        except _Transient as e:
            if attempt >= retries:
                raise _Permanent(str(e))  # give up -> record with the transient reason
            attempt += 1
            await asyncio.sleep(min(2 ** attempt, 5))


# ---------- GPU work (runs in a worker thread) ----------
def _process_image(conn, job_id: str, image_id: str, image_bytes: bytes, config_key: str) -> int:
    width, height, crops = detection_service.detect_products(image_bytes)

    rows: list[db.DetectionRow] = []
    if crops:
        crop_bytes = [cbytes for cbytes, _ in crops]
        labels = classifier.classify_batch(
            crop_bytes, candidate_labels=model_config.active_known_labels()
        )
        model_id = model_config.active_model_id()
        for (_, (x1, y1, x2, y2)), (class_name, _is_unknown) in zip(crops, labels):
            x_center = ((x1 + x2) / 2) / width
            y_center = ((y1 + y2) / 2) / height
            bbox_width = (x2 - x1) / width
            bbox_height = (y2 - y1) / height
            rows.append((
                uuid.uuid4().hex,   # row id, carried to the remote so a re-send is safe
                image_id, class_name,
                x_center, y_center, bbox_width, bbox_height,
                model_id,
            ))

    # Detections, the ledger row and the "this image is done" mark commit
    # together, so a crash can never duplicate rows on resume -- nor leave the
    # ledger claiming an image was processed when its rows were rolled back.
    return db.complete_item(conn, job_id, image_id, rows, config_key)


# ---------- Orchestration ----------
async def _run(job: DataDumpJob) -> None:
    job.status = "running"
    job.started_at = job.started_at or _now()
    job.error = None

    # Fail fast if the database is unreachable.
    try:
        await asyncio.to_thread(db.ping)
    except Exception as e:
        job.status = "failed"
        job.error = f"Database unreachable: {e}"
        job.finished_at = _now()
        _LIVE.pop(job.job_id, None)
        logger.error("Data dump %s aborted: %s", job.job_id, e)
        return

    # work_conn is driven only by the GPU consumer thread; meta_conn handles
    # bookkeeping from the event loop. Separate connections, because a commit
    # is connection-wide and would otherwise cut a detection insert in half.
    work_conn = await asyncio.to_thread(db.connect)
    meta_conn = await asyncio.to_thread(db.connect, True)
    meta_lock = asyncio.Lock()

    async def mark_failed(image_id: str, url: str, reason: str) -> None:
        del url  # recorded on the item row by mark_item_failed
        job.record_failure()
        job.pending_images = max(0, job.pending_images - 1)
        async with meta_lock:
            try:
                await asyncio.to_thread(db.mark_item_failed, meta_conn, job.job_id, image_id, reason)
            except Exception as e:  # noqa: BLE001 - bookkeeping must not kill the run
                logger.error("Data dump %s: could not record failure for %s: %s", job.job_id, image_id, e)

    try:
        # Derived now rather than at upload time, so a resume after a model
        # change is recorded under the setup that actually produced the rows.
        config_key = await asyncio.to_thread(model_config.active_config_key)
        job.config_key = config_key

        skipped = await asyncio.to_thread(
            db.skip_already_processed, meta_conn, job.job_id, config_key
        )
        if skipped:
            job.skipped_images += skipped
            logger.info(
                "Data dump %s: skipped %d image(s) already processed under config %s",
                job.job_id, skipped, config_key,
            )

        pending = await asyncio.to_thread(db.pending_items, meta_conn, job.job_id)
        job.pending_images = len(pending)
        if not pending:
            job.status = "completed"
            await asyncio.to_thread(
                db.set_job_status, meta_conn, job.job_id, "completed", finished=True
            )
            job.finished_at = _now()
            return

        await asyncio.to_thread(
            db.set_job_status, meta_conn, job.job_id, "running", started=True
        )

        ready: asyncio.Queue = asyncio.Queue(maxsize=config.DATA_DUMP_QUEUE_MAX)
        row_q: asyncio.Queue = asyncio.Queue()
        for row in pending:
            row_q.put_nowait(row)

        timeout = httpx.Timeout(
            connect=config.DATA_DUMP_CONNECT_TIMEOUT,
            read=config.DATA_DUMP_READ_TIMEOUT,
            write=config.DATA_DUMP_CONNECT_TIMEOUT,
            pool=None,
        )
        n_workers = max(1, min(config.DATA_DUMP_DOWNLOAD_CONCURRENCY, len(pending)))

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "ShelfAnalytics/1.0 (+data-dump)"},
        ) as client:

            async def downloader() -> None:
                while True:
                    try:
                        image_id, url = row_q.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    try:
                        if job.cancel_requested:
                            continue  # drain remaining rows without downloading
                        try:
                            data = await _download(client, url, config.DATA_DUMP_RETRIES)
                            await ready.put((image_id, url, data))
                        except _Permanent as e:
                            await mark_failed(image_id, url, str(e))
                        except Exception as e:  # noqa: BLE001 - never let one URL kill a worker
                            await mark_failed(image_id, url, f"download_error: {e}")
                    finally:
                        row_q.task_done()

            async def produce() -> None:
                await asyncio.gather(*[downloader() for _ in range(n_workers)])
                await ready.put(_SENTINEL)

            async def consume() -> None:
                while True:
                    item = await ready.get()
                    try:
                        if item is _SENTINEL:
                            return
                        image_id, url, data = item
                        if job.cancel_requested:
                            continue
                        try:
                            written = await asyncio.to_thread(
                                _process_image, work_conn, job.job_id, image_id, data, config_key
                            )
                            job.rows_written += written
                            job.processed_images += 1
                            job.pending_images = max(0, job.pending_images - 1)
                        except Exception as e:  # noqa: BLE001
                            await mark_failed(image_id, url, f"inference_error: {e}")
                            logger.exception("Data dump %s: image %s failed", job.job_id, image_id)
                    finally:
                        ready.task_done()

            await asyncio.gather(produce(), consume())

        job.status = "canceled" if job.cancel_requested else "completed"
        await asyncio.to_thread(
            db.set_job_status, meta_conn, job.job_id, job.status, finished=True
        )
    except Exception as e:  # noqa: BLE001
        job.status = "failed"
        job.error = str(e)
        logger.exception("Data dump %s crashed", job.job_id)
        try:
            await asyncio.to_thread(
                db.set_job_status, meta_conn, job.job_id, "failed", error=str(e), finished=True
            )
        except Exception:  # noqa: BLE001
            logger.exception("Data dump %s: could not persist failed status", job.job_id)
    finally:
        job.finished_at = _now()
        _LIVE.pop(job.job_id, None)
        for conn in (work_conn, meta_conn):
            try:
                await asyncio.to_thread(conn.close)
            except Exception:  # noqa: BLE001
                pass
