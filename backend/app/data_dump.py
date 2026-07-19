"""Database Data Dump pipeline.

CSV of ``(image_id, image_url)`` -> download each image -> detect (YOLO, optional
SAHI) -> classify (SwinV2) -> insert rows into the Postgres ``product_detections``
table. Images and crops live in memory only and are discarded after each image;
nothing is written to disk.

The run is a background job: downloads run concurrently and feed a bounded queue,
while a single GPU consumer processes one image at a time (classifying its crops
in batches). Callers start a job and poll its status.
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
    if data[:3] in _IMAGE_MAGIC or data.startswith(_IMAGE_MAGIC):
        return True
    if data[:2] == b"BM":
        return True
    if data[8:12] == b"WEBP":  # RIFF....WEBP
        return True
    return any(data.startswith(sig) for sig in _IMAGE_MAGIC)


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
    for record in reader:
        image_id = str(record.get(id_col, "") or "").strip()
        image_url = str(record.get(url_col, "") or "").strip()
        if image_id and image_url:
            rows.append((image_id, image_url))
    if not rows:
        return [], "No valid (image_id, image_url) rows found."
    return rows, None


# ---------- Job model ----------
@dataclass
class _Failure:
    image_id: str
    image_url: str
    reason: str


@dataclass
class DataDumpJob:
    job_id: str
    source_filename: str
    total_images: int
    status: str = "queued"  # queued | running | completed | failed | canceled
    processed_images: int = 0
    failed_images: int = 0
    rows_written: int = 0
    detections: int = 0
    error: str | None = None
    created_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    failures: list[_Failure] = field(default_factory=list)
    cancel_requested: bool = False

    def record_failure(self, image_id: str, image_url: str, reason: str) -> None:
        self.failed_images += 1
        if len(self.failures) < config.DATA_DUMP_MAX_FAILURES_TRACKED:
            self.failures.append(_Failure(image_id, image_url, reason))

    def snapshot(self) -> dict:
        return {
            "job_id": self.job_id,
            "source_filename": self.source_filename,
            "status": self.status,
            "total_images": self.total_images,
            "processed_images": self.processed_images,
            "failed_images": self.failed_images,
            "rows_written": self.rows_written,
            "detections": self.detections,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "failures": [
                {"image_id": f.image_id, "image_url": f.image_url, "reason": f.reason}
                for f in self.failures
            ],
            "failures_truncated": self.failed_images > len(self.failures),
        }


_JOBS: dict[str, DataDumpJob] = {}
_TASKS: set[asyncio.Task] = set()


def get_job(job_id: str) -> DataDumpJob | None:
    return _JOBS.get(job_id)


def list_jobs() -> list[DataDumpJob]:
    return sorted(_JOBS.values(), key=lambda j: j.created_at, reverse=True)


def request_cancel(job_id: str) -> bool:
    job = _JOBS.get(job_id)
    if not job or job.status not in ("queued", "running"):
        return False
    job.cancel_requested = True
    return True


def start_job(source_filename: str, rows: list[tuple[str, str]]) -> DataDumpJob:
    job = DataDumpJob(
        job_id=uuid.uuid4().hex[:12],
        source_filename=source_filename,
        total_images=len(rows),
    )
    _JOBS[job.job_id] = job
    task = asyncio.create_task(_run(job, rows))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return job


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
def _process_image(conn, image_id: str, image_bytes: bytes) -> int:
    width, height, crops = detection_service.detect_products(image_bytes)
    if not crops:
        return 0

    crop_bytes = [cbytes for cbytes, _ in crops]
    labels = classifier.classify_batch(crop_bytes, candidate_labels=model_config.active_known_labels())

    rows: list[db.DetectionRow] = []
    for (_, (x1, y1, x2, y2)), (class_name, _is_unknown) in zip(crops, labels):
        x_center = ((x1 + x2) / 2) / width
        y_center = ((y1 + y2) / 2) / height
        bbox_width = (x2 - x1) / width
        bbox_height = (y2 - y1) / height
        rows.append((image_id, class_name, x_center, y_center, bbox_width, bbox_height))

    return db.insert_detections(conn, rows)


# ---------- Orchestration ----------
async def _run(job: DataDumpJob, rows: list[tuple[str, str]]) -> None:
    job.status = "running"
    job.started_at = _now()

    # Fail fast if the database is unreachable.
    try:
        await asyncio.to_thread(db.ping)
    except Exception as e:
        job.status = "failed"
        job.error = f"Database unreachable: {e}"
        job.finished_at = _now()
        logger.error("Data dump %s aborted: %s", job.job_id, e)
        return

    conn = await asyncio.to_thread(db.connect)
    ready: asyncio.Queue = asyncio.Queue(maxsize=config.DATA_DUMP_QUEUE_MAX)
    row_q: asyncio.Queue = asyncio.Queue()
    for row in rows:
        row_q.put_nowait(row)

    timeout = httpx.Timeout(
        connect=config.DATA_DUMP_CONNECT_TIMEOUT,
        read=config.DATA_DUMP_READ_TIMEOUT,
        write=config.DATA_DUMP_CONNECT_TIMEOUT,
        pool=None,
    )
    n_workers = max(1, min(config.DATA_DUMP_DOWNLOAD_CONCURRENCY, len(rows)))

    try:
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
                            job.record_failure(image_id, url, str(e))
                        except Exception as e:  # noqa: BLE001 - never let one URL kill a worker
                            job.record_failure(image_id, url, f"download_error: {e}")
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
                            written = await asyncio.to_thread(_process_image, conn, image_id, data)
                            job.rows_written += written
                            job.detections += written
                            job.processed_images += 1
                        except Exception as e:  # noqa: BLE001
                            job.record_failure(image_id, url, f"inference_error: {e}")
                            logger.exception("Data dump %s: image %s failed", job.job_id, image_id)
                    finally:
                        ready.task_done()

            await asyncio.gather(produce(), consume())

        job.status = "canceled" if job.cancel_requested else "completed"
    except Exception as e:  # noqa: BLE001
        job.status = "failed"
        job.error = str(e)
        logger.exception("Data dump %s crashed", job.job_id)
    finally:
        await asyncio.to_thread(conn.close)
        job.finished_at = _now()
