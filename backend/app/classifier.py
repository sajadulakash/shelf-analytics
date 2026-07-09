"""SwinV2-based local classifier for cropped product images."""

import io
import json
import logging
import uuid
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForImageClassification

from app import config
from app.models import ClassificationRecord, ImageClassificationResult

logger = logging.getLogger(__name__)

_PROCESSOR: AutoImageProcessor | None = None
_MODEL: AutoModelForImageClassification | None = None
_LABELS: list[str] | None = None
UNKNOWN_REPORT_LABEL = "Unknown"


def _load_classifier() -> tuple[AutoImageProcessor, AutoModelForImageClassification, list[str]]:
    global _PROCESSOR, _MODEL, _LABELS

    if _PROCESSOR is not None and _MODEL is not None and _LABELS is not None:
        return _PROCESSOR, _MODEL, _LABELS

    model_dir = config.SWINV2_MODEL_DIR
    if not model_dir.exists():
        raise FileNotFoundError(f"SwinV2 model directory not found: {model_dir}")

    _PROCESSOR = AutoImageProcessor.from_pretrained(str(model_dir), local_files_only=True)
    _MODEL = AutoModelForImageClassification.from_pretrained(str(model_dir), local_files_only=True)
    _MODEL.eval()

    id2label = getattr(_MODEL.config, "id2label", {}) or {}
    if id2label:
        ordered = sorted((int(k), v) for k, v in id2label.items())
        _LABELS = [label for _, label in ordered]
    else:
        _LABELS = [f"label_{idx}" for idx in range(_MODEL.config.num_labels)]

    return _PROCESSOR, _MODEL, _LABELS


def _save_image(image_bytes: bytes, original_filename: str) -> Path:
    ext = Path(original_filename).suffix or ".jpg"
    dest = config.UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    dest.write_bytes(image_bytes)
    return dest


def _save_record(record: ClassificationRecord) -> None:
    log_file = config.RESULTS_DIR / "classification_log.jsonl"
    with open(log_file, "a") as f:
        f.write(record.model_dump_json() + "\n")


def available_labels() -> list[str]:
    """Return class labels configured in the local SwinV2 model."""
    config_path = config.SWINV2_MODEL_DIR / "config.json"
    if config_path.exists():
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        id2label = payload.get("id2label", {})
        if isinstance(id2label, dict) and id2label:
            ordered = sorted((int(k), str(v)) for k, v in id2label.items())
            return [label for _, label in ordered]

    _, _, labels = _load_classifier()
    return list(labels)


def _predict(image_bytes: bytes) -> tuple[str, float]:
    processor, model, labels = _load_classifier()

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

    best_index = int(torch.argmax(probs, dim=-1)[0].item())
    confidence = float(probs[0, best_index].item())
    label = labels[best_index] if best_index < len(labels) else "Unknown"
    return label, confidence


def _label_key(label: str) -> str:
    return str(label).strip().casefold().replace("_", "-")


def _is_unknown_product_label(label: str) -> bool:
    key = _label_key(label)
    # Any class named like "unknown", "unknown-products", "unknown_53", ... is an
    # unknown bucket, never a matched product.
    if key.startswith("unknown"):
        return True
    unknown_keys = {_label_key(item) for item in config.UNKNOWN_PRODUCT_LABELS}
    return key in unknown_keys


def classify_single(
    image_bytes: bytes,
    filename: str,
    candidate_labels: list[str] | None = None,
    mime_type: str = "image/jpeg",
) -> ImageClassificationResult:
    """Classify one crop using the local SwinV2 model."""

    del mime_type

    saved_path = _save_image(image_bytes, filename)

    try:
        predicted_label, confidence = _predict(image_bytes)
        reason = None

        if _is_unknown_product_label(predicted_label):
            reason = f"Model predicted unknown product class '{predicted_label}'."
            predicted_label = UNKNOWN_REPORT_LABEL
        elif candidate_labels and predicted_label not in candidate_labels:
            reason = f"Predicted class '{predicted_label}' is outside requested labels."
            predicted_label = UNKNOWN_REPORT_LABEL
            confidence = 0.0

        if confidence < config.SWINV2_CONFIDENCE_THRESHOLD and predicted_label != UNKNOWN_REPORT_LABEL:
            reason = (
                f"Low confidence ({confidence:.2f}) below threshold "
                f"{config.SWINV2_CONFIDENCE_THRESHOLD:.2f}."
            )
            predicted_label = UNKNOWN_REPORT_LABEL

        is_unknown = predicted_label == UNKNOWN_REPORT_LABEL
    except Exception as e:
        logger.error("SwinV2 classification failed for %s: %s", filename, e)
        predicted_label = UNKNOWN_REPORT_LABEL
        confidence = 0.0
        is_unknown = True
        reason = f"SwinV2 error: {e}"

    result = ImageClassificationResult(
        filename=filename,
        predicted_label=predicted_label,
        confidence=confidence,
        is_unknown=is_unknown,
        reason=reason,
        ocr_text="",
        vision_labels=[],
    )

    record = ClassificationRecord(
        filename=filename,
        image_path=str(saved_path),
        ocr_text="",
        vision_labels=[],
        predicted_label=predicted_label,
        confidence=confidence,
        is_unknown=is_unknown,
        reason=reason,
    )
    try:
        _save_record(record)
    except Exception as e:
        logger.error("Failed to save record for %s: %s", filename, e)

    return result
