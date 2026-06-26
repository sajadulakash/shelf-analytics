"""FastAPI application – Product Classification Service."""

import asyncio
import base64
import logging
import json
import uuid
from pathlib import Path
from collections import Counter
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import config
from app.models import (
    ClassificationResponse,
    DetectionBox,
    CropClassificationResult,
    DetectedCrop,
    ShelfDetectionResponse,
    ShelfClassificationResponse,
    ShopReportRow,
    ShopTaskInput,
    ShopTaskListResponse,
    ShopTaskReportResponse,
    LabelSettingsResponse,
    LabelSettingsUpdate,
)
from app.classifier import UNKNOWN_REPORT_LABEL, available_labels, classify_single
from app.detection_service import detect_and_crop_products

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ShelfAnalytics – Product Classification Service",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------- Global error handler ----------
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ---------- Health check ----------
@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------- Frontend ----------
@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/labels")
async def labels_page():
    return FileResponse(
        str(STATIC_DIR / "labels.html"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@app.get("/con")
async def confidence_page():
    return FileResponse(str(STATIC_DIR / "con.html"))


@app.get("/process")
async def process_page():
    return FileResponse(str(STATIC_DIR / "process.html"))


def _normalize_labels(labels: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for label in labels:
        cleaned = str(label).strip()
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


def _label_key(label: str) -> str:
    return str(label).strip().casefold().replace("_", "-")


def _is_unknown_report_label(label: str) -> bool:
    unknown_keys = {_label_key(item) for item in config.UNKNOWN_PRODUCT_LABELS}
    unknown_keys.add(_label_key(UNKNOWN_REPORT_LABEL))
    return _label_key(label) in unknown_keys


def _load_managed_labels() -> list[str] | None:
    path = config.MANAGED_LABELS_FILE
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    labels = payload.get("labels", []) if isinstance(payload, dict) else []
    if not isinstance(labels, list):
        return None

    normalized = _normalize_labels(labels)
    return normalized or None


def _save_managed_labels(labels: list[str]) -> list[str]:
    normalized = _normalize_labels(labels)
    if not normalized:
        raise HTTPException(status_code=400, detail="At least one label is required.")

    config.MANAGED_LABELS_FILE.write_text(
        json.dumps({"labels": normalized}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def _current_labels() -> list[str]:
    managed = _load_managed_labels()
    if managed:
        return managed
    return available_labels()


@app.get("/api/labels", response_model=LabelSettingsResponse)
async def get_label_settings():
    return LabelSettingsResponse(labels=_current_labels(), default_labels=available_labels())


@app.put("/api/labels", response_model=LabelSettingsResponse)
async def update_label_settings(payload: LabelSettingsUpdate):
    labels = _save_managed_labels(payload.labels)
    return LabelSettingsResponse(labels=labels, default_labels=available_labels())


def _resolve_candidate_labels(labels: str | None) -> list[str]:
    if labels and labels.strip():
        return _normalize_labels(labels.split(","))

    return _current_labels()


def _safe_stem(name: str) -> str:
    return "".join(ch for ch in Path(name).stem if ch.isalnum() or ch in ("-", "_")) or "image"


def _write_bytes(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _public_upload_url(path: Path) -> str:
    rel = path.relative_to(config.BASE_DIR / "uploads")
    return f"/uploads/{rel.as_posix()}"


def _run_manifest_path(run_id: str) -> Path:
    return config.RUNS_DIR / f"{run_id}.json"


def _write_manifest(run_id: str, payload: dict) -> None:
    _run_manifest_path(run_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _read_manifest(run_id: str) -> dict:
    path = _run_manifest_path(run_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_recent_confidence_records(limit: int = 100) -> list[dict]:
    log_path = config.RESULTS_DIR / "classification_log.jsonl"
    if not log_path.exists():
        return []

    limit = max(1, min(limit, 500))
    records: list[dict] = []
    for line in reversed(log_path.read_text(encoding="utf-8").splitlines()):
        if len(records) >= limit:
            break
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        records.append(
            {
                "filename": payload.get("filename", ""),
                "predicted_label": payload.get("predicted_label", UNKNOWN_REPORT_LABEL),
                "confidence": float(payload.get("confidence") or 0.0),
                "is_unknown": bool(payload.get("is_unknown")),
                "reason": payload.get("reason"),
            }
        )
    return records


@app.get("/api/confidence")
async def confidence_records(limit: int = 100):
    return {
        "threshold": config.SWINV2_CONFIDENCE_THRESHOLD,
        "records": _read_recent_confidence_records(limit),
    }


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def _shop_image_files(shop_dir: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in shop_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        ],
        key=lambda path: path.name.casefold(),
    )


def _task_shop_inputs() -> list[ShopTaskInput]:
    if not config.SHOP_IMAGES_DIR.exists():
        return []

    shops: list[ShopTaskInput] = []
    for shop_dir in sorted(config.SHOP_IMAGES_DIR.iterdir(), key=lambda path: path.name.casefold()):
        if not shop_dir.is_dir():
            continue
        shops.append(
            ShopTaskInput(
                shop_name=shop_dir.name,
                image_count=len(_shop_image_files(shop_dir)),
            )
        )
    return shops


def _resolve_shop_dir(shop_name: str) -> Path:
    cleaned = str(shop_name).strip()
    if not cleaned or Path(cleaned).name != cleaned:
        raise HTTPException(status_code=400, detail="Invalid shop name.")

    shop_dir = config.SHOP_IMAGES_DIR / cleaned
    if not shop_dir.exists() or not shop_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Shop folder not found: {cleaned}")
    return shop_dir


async def _classify_shop_crop(
    crop_image_bytes: bytes,
    filename: str,
    candidate_labels: list[str],
    semaphore: asyncio.Semaphore,
) -> tuple[str, bool]:
    async with semaphore:
        classified = await asyncio.to_thread(
            classify_single,
            image_bytes=crop_image_bytes,
            filename=filename,
            candidate_labels=candidate_labels,
            mime_type="image/jpeg",
        )
    label = UNKNOWN_REPORT_LABEL if classified.is_unknown else classified.predicted_label
    return label, classified.is_unknown


async def _analyze_shop_folder(shop_name: str) -> ShopReportRow:
    shop_dir = _resolve_shop_dir(shop_name)
    image_files = _shop_image_files(shop_dir)
    candidate_labels = _resolve_candidate_labels(None)
    existing_labels = sorted(candidate_labels)
    errors: list[str] = []
    crop_tasks = []
    semaphore = asyncio.Semaphore(config.CLASSIFICATION_CONCURRENCY)
    total_detections = 0

    for image_file in image_files:
        try:
            _, detection_crops = detect_and_crop_products(image_bytes=image_file.read_bytes())
        except Exception as e:
            logger.error("Shop image analysis failed for %s/%s: %s", shop_name, image_file.name, e)
            errors.append(f"{image_file.name}: {e}")
            continue

        total_detections += len(detection_crops)
        for idx, crop in enumerate(detection_crops, start=1):
            crop_name = f"{shop_name}-{image_file.stem}-crop-{idx:03d}.jpg"
            crop_tasks.append(
                _classify_shop_crop(crop.image_bytes, crop_name, candidate_labels, semaphore)
            )

    label_counter: Counter[str] = Counter()
    unknown_count = 0
    if crop_tasks:
        for label, is_unknown in await asyncio.gather(*crop_tasks):
            label_counter[label] += 1
            if is_unknown:
                unknown_count += 1

    missing_labels = sorted([
        label
        for label in existing_labels
        if not _is_unknown_report_label(label) and label_counter.get(label, 0) == 0
    ])

    return ShopReportRow(
        shop_name=shop_name,
        image_count=len(image_files),
        total_detections=total_detections,
        product_counts=dict(label_counter),
        unknown_count=unknown_count,
        existing_labels=existing_labels,
        missing_labels=missing_labels,
        errors=errors,
    )


def _build_task_report(rows: list[ShopReportRow]) -> ShopTaskReportResponse:
    totals: Counter[str] = Counter()
    labels: set[str] = set()
    unknown_count = 0

    for row in rows:
        labels.update(row.existing_labels)
        labels.update(row.product_counts)
        totals.update(row.product_counts)
        unknown_count += row.unknown_count

    return ShopTaskReportResponse(
        image_root=str(config.SHOP_IMAGES_DIR),
        shops=rows,
        labels=sorted(labels),
        totals=dict(totals),
        unknown_count=unknown_count,
    )


@app.get("/api/task-shops", response_model=ShopTaskListResponse)
async def task_shops():
    return ShopTaskListResponse(
        image_root=str(config.SHOP_IMAGES_DIR),
        shops=_task_shop_inputs(),
    )


@app.post("/api/analyze-shop", response_model=ShopReportRow)
async def analyze_shop(
    shop_name: str = Form(..., description="Shop folder name under SHOP_IMAGES_DIR."),
):
    return await _analyze_shop_folder(shop_name)


@app.post("/api/task-report", response_model=ShopTaskReportResponse)
async def task_report():
    rows = []
    for shop in _task_shop_inputs():
        rows.append(await _analyze_shop_folder(shop.shop_name))
    return _build_task_report(rows)


# ---------- Classification endpoint ----------
@app.post("/classify-products", response_model=ClassificationResponse)
async def classify_products(
    images: list[UploadFile] = File(..., description="One or more cropped product images"),
    labels: str = Form(
        default=None,
        description="Optional comma-separated label filter. Omit to use all SwinV2 labels.",
    ),
):
    """Classify each uploaded crop with the local SwinV2 model."""

    if not images:
        raise HTTPException(status_code=400, detail="No images provided.")

    candidate_labels = _resolve_candidate_labels(labels)

    if not candidate_labels:
        raise HTTPException(status_code=500, detail="No labels available from SwinV2 model.")

    results = []
    for upload in images:
        try:
            image_bytes = await upload.read()
            if not image_bytes:
                raise ValueError("Empty file")

            mime = upload.content_type or "image/jpeg"
            result = classify_single(
                image_bytes=image_bytes,
                filename=upload.filename or "unknown.jpg",
                candidate_labels=candidate_labels,
                mime_type=mime,
            )
            results.append(result)
        except Exception as e:
            logger.error("Error processing %s: %s", upload.filename, e)
            from app.models import ImageClassificationResult
            results.append(ImageClassificationResult(
                filename=upload.filename or "unknown.jpg",
                predicted_label="Unknown",
                confidence=0.0,
                is_unknown=True,
                reason=f"Processing error: {e}",
            ))

    # Aggregated counts, including unknown products in the report bucket.
    label_counter = Counter(
        UNKNOWN_REPORT_LABEL if r.is_unknown else r.predicted_label
        for r in results
    )
    unknown_count = sum(1 for r in results if r.is_unknown)

    return ClassificationResponse(
        total_images=len(results),
        results=results,
        label_counts=dict(label_counter),
        unknown_count=unknown_count,
    )


@app.post("/detect-shelf", response_model=ShelfDetectionResponse)
async def detect_shelf(
    image: UploadFile = File(..., description="One raw shelf image with multiple products"),
    labels: str = Form(default=None, description="Optional comma-separated candidate labels."),
):
    if image is None:
        raise HTTPException(status_code=400, detail="No image provided.")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")

    base_name = _safe_stem(image.filename or "shelf")
    run_id = uuid.uuid4().hex[:10]
    raw_name = f"{base_name}-{run_id}.jpg"
    raw_path = config.RAW_UPLOAD_DIR / raw_name
    _write_bytes(raw_path, image_bytes)

    try:
        detection_bytes, detection_crops = detect_and_crop_products(image_bytes=image_bytes)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Detection failed: {e}")

    detection_name = f"{base_name}-{run_id}-detected.jpg"
    detection_path = config.DETECTION_DIR / detection_name
    _write_bytes(detection_path, detection_bytes)

    candidate_labels = _resolve_candidate_labels(labels)
    existing_labels = sorted(candidate_labels)

    detected_crops: list[DetectedCrop] = []
    manifest_crops: list[dict] = []

    for idx, crop in enumerate(detection_crops, start=1):
        crop_name = f"{base_name}-{run_id}-crop-{idx:03d}.jpg"
        crop_path = config.UPLOAD_DIR / crop_name
        _write_bytes(crop_path, crop.image_bytes)

        detected_crops.append(
            DetectedCrop(
                crop_filename=crop_name,
                crop_url=_public_upload_url(crop_path),
                crop_image_b64=base64.b64encode(crop.image_bytes).decode(),
                bbox=DetectionBox(**crop.bbox),
            )
        )
        manifest_crops.append(
            {
                "crop_filename": crop_name,
                "crop_path": str(crop_path),
                "bbox": crop.bbox,
            }
        )

    _write_manifest(
        run_id,
        {
            "run_id": run_id,
            "raw_filename": image.filename or raw_name,
            "candidate_labels": candidate_labels,
            "existing_labels": existing_labels,
            "detection_image_url": _public_upload_url(detection_path),
            "crops": manifest_crops,
        },
    )

    return ShelfDetectionResponse(
        run_id=run_id,
        raw_filename=image.filename or raw_name,
        detection_image_url=_public_upload_url(detection_path),
        detection_image_b64=base64.b64encode(detection_bytes).decode(),
        total_detections=len(detected_crops),
        crops=detected_crops,
        existing_labels=existing_labels,
    )


async def _classify_one_crop(
    crop: dict,
    candidate_labels: list[str],
    semaphore: asyncio.Semaphore,
) -> CropClassificationResult:
    """Classify a single crop, respecting the concurrency semaphore."""
    crop_name = crop["crop_filename"]
    crop_path = Path(crop["crop_path"])
    bbox = crop["bbox"]

    crop_b64 = ""
    if not crop_path.exists():
        return CropClassificationResult(
            crop_filename=crop_name,
            crop_url=_public_upload_url(crop_path),
            crop_image_b64=crop_b64,
            bbox=DetectionBox(**bbox),
            predicted_label="Unknown",
            confidence=0.0,
            is_unknown=True,
            reason=f"Crop file missing: {crop_path.name}",
        )

    crop_bytes = crop_path.read_bytes()
    crop_b64 = base64.b64encode(crop_bytes).decode()

    async with semaphore:
        try:
            classified = await asyncio.to_thread(
                classify_single,
                image_bytes=crop_bytes,
                filename=crop_name,
                candidate_labels=candidate_labels,
                mime_type="image/jpeg",
            )
            return CropClassificationResult(
                crop_filename=crop_name,
                crop_url=_public_upload_url(crop_path),
                crop_image_b64=crop_b64,
                bbox=DetectionBox(**bbox),
                predicted_label=classified.predicted_label,
                confidence=classified.confidence,
                is_unknown=classified.is_unknown,
                reason=classified.reason,
            )
        except Exception as e:
            logger.error("Crop classification failed for %s: %s", crop_name, e)
            return CropClassificationResult(
                crop_filename=crop_name,
                crop_url=_public_upload_url(crop_path),
                crop_image_b64=crop_b64,
                bbox=DetectionBox(**bbox),
                predicted_label="Unknown",
                confidence=0.0,
                is_unknown=True,
                reason=f"Processing error: {e}",
            )


@app.post("/classify-detected-crops", response_model=ShelfClassificationResponse)
async def classify_detected_crops(
    run_id: str = Form(..., description="Run ID returned by /detect-shelf"),
):
    manifest = _read_manifest(run_id)
    candidate_labels = manifest.get("candidate_labels", [])
    existing_labels = manifest.get("existing_labels", candidate_labels)
    manifest_crops = manifest.get("crops", [])

    if not manifest_crops:
        return ShelfClassificationResponse(
            run_id=run_id,
            total_detections=0,
            classifications=[],
            label_counts={},
            unknown_count=0,
            existing_labels=existing_labels,
            missing_labels=sorted([
                label
                for label in existing_labels
                if not _is_unknown_report_label(label)
            ]),
        )

    semaphore = asyncio.Semaphore(config.CLASSIFICATION_CONCURRENCY)
    tasks = [
        _classify_one_crop(crop, candidate_labels, semaphore)
        for crop in manifest_crops
    ]
    classification_results: list[CropClassificationResult] = await asyncio.gather(*tasks)

    label_counter: Counter[str] = Counter()
    unknown_count = 0
    for result in classification_results:
        if result.is_unknown:
            unknown_count += 1
            label_counter[UNKNOWN_REPORT_LABEL] += 1
        else:
            label_counter[result.predicted_label] += 1

    missing_labels = sorted([
        label
        for label in existing_labels
        if not _is_unknown_report_label(label) and label_counter.get(label, 0) == 0
    ])

    return ShelfClassificationResponse(
        run_id=run_id,
        total_detections=len(classification_results),
        classifications=list(classification_results),
        label_counts=dict(label_counter),
        unknown_count=unknown_count,
        existing_labels=existing_labels,
        missing_labels=missing_labels,
    )


# ---------- Serve uploaded images (must be AFTER all route definitions) ----------
UPLOADS_DIR = config.BASE_DIR / "uploads"
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
