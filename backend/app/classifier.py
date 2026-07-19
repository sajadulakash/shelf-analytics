"""SwinV2-based local classifier for cropped product images."""

import io
import json
import logging
import uuid
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForImageClassification

from app import config, model_config
from app.models import ClassificationRecord, ImageClassificationResult

logger = logging.getLogger(__name__)

# Loaded classifiers cached by model directory, so switching models in the
# Model Configuration page loads the newly-selected one on next use.
_CLASSIFIERS: dict[str, tuple] = {}
UNKNOWN_REPORT_LABEL = "Unknown"


def _device() -> str:
    """GPU when available, else CPU (honours CLASSIFIER_DEVICE)."""
    return config.CLASSIFIER_DEVICE if torch.cuda.is_available() else "cpu"


def _load_classifier(model_dir: Path) -> tuple[AutoImageProcessor, AutoModelForImageClassification, list[str]]:
    key = str(model_dir)
    if key in _CLASSIFIERS:
        return _CLASSIFIERS[key]

    if not model_dir.exists():
        raise FileNotFoundError(f"SwinV2 model directory not found: {model_dir}")

    processor = AutoImageProcessor.from_pretrained(key, local_files_only=True)
    model = AutoModelForImageClassification.from_pretrained(key, local_files_only=True)
    model.to(_device()).eval()

    id2label = getattr(model.config, "id2label", {}) or {}
    if id2label:
        ordered = sorted((int(k), v) for k, v in id2label.items())
        labels = [label for _, label in ordered]
    else:
        labels = [f"label_{idx}" for idx in range(model.config.num_labels)]

    _CLASSIFIERS[key] = (processor, model, labels)
    return _CLASSIFIERS[key]


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
    """Return class labels configured in the active SwinV2 model."""
    labels = model_config.labels_for(model_config.load()["classification_model"])
    if labels:
        return labels

    _, _, loaded = _load_classifier(model_config.active_classification_dir())
    return list(loaded)


def _predict(image_bytes: bytes) -> tuple[str, float]:
    processor, model, labels = _load_classifier(model_config.active_classification_dir())

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    inputs = processor(images=image, return_tensors="pt").to(model.device)

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


def _resolve_label(
    predicted_label: str,
    confidence: float,
    candidate_labels: list[str] | None,
) -> tuple[str, bool]:
    """Apply the unknown/threshold/candidate rules → (final_label, is_unknown)."""
    if _is_unknown_product_label(predicted_label):
        return UNKNOWN_REPORT_LABEL, True
    if candidate_labels and predicted_label not in candidate_labels:
        return UNKNOWN_REPORT_LABEL, True
    if confidence < config.SWINV2_CONFIDENCE_THRESHOLD:
        return UNKNOWN_REPORT_LABEL, True
    return predicted_label, False


def classify_batch(
    crops: list[bytes],
    candidate_labels: list[str] | None = None,
    batch_size: int | None = None,
) -> list[tuple[str, bool]]:
    """Classify many crops in GPU batches. In-memory only — no disk, no logging.

    Returns one ``(class_name, is_unknown)`` per crop, in input order. Used by the
    Database Data Dump pipeline where crops are never persisted.
    """
    if not crops:
        return []

    processor, model, labels = _load_classifier(model_config.active_classification_dir())
    batch_size = batch_size or config.DATA_DUMP_CLASSIFY_BATCH

    results: list[tuple[str, bool]] = []
    for start in range(0, len(crops), batch_size):
        chunk = crops[start:start + batch_size]
        images = [Image.open(io.BytesIO(b)).convert("RGB") for b in chunk]
        inputs = processor(images=images, return_tensors="pt").to(model.device)

        with torch.no_grad():
            logits = model(**inputs).logits
            probs = torch.nn.functional.softmax(logits, dim=-1)

        confs, idxs = torch.max(probs, dim=-1)
        for i in range(len(chunk)):
            best_index = int(idxs[i].item())
            confidence = float(confs[i].item())
            predicted = labels[best_index] if best_index < len(labels) else UNKNOWN_REPORT_LABEL
            results.append(_resolve_label(predicted, confidence, candidate_labels))

    return results


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
