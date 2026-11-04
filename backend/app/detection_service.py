"""Product detection and crop extraction.

The selected detection model decides how detection runs:

* **YOLO** (a ``.pt`` file): SAHI (Slicing Aided Hyper Inference) tiles the
  high-resolution shelf image and merges the per-slice predictions, or, with
  SAHI off, a single full-frame ``YOLO.predict`` pass.
* **RF-DETR style ONNX** (a model folder with ``model_info.json``): one pass
  over the whole image at the model's input size, with the model's own
  confidence cut-off - see ``onnx_detector``.

Every path produces the same crop/bbox contract.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image
from ultralytics import YOLO

from app import config, model_config, onnx_detector


@dataclass
class DetectionCrop:
    image_bytes: bytes
    bbox: dict[str, Any]


# A single normalized detection before cropping: absolute xyxy plus metadata.
@dataclass
class _RawBox:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    class_id: int
    class_name: str


# Loaded models are cached by weights path so switching models in the Model
# Configuration page loads the newly-selected one on next use.
_YOLO_CACHE: dict[str, YOLO] = {}
_SAHI_CACHE: dict[str, Any] = {}


def _get_model(model_path: Path) -> YOLO:
    key = str(model_path)
    if key not in _YOLO_CACHE:
        if not model_path.exists():
            raise FileNotFoundError(f"YOLO model not found: {model_path}")
        _YOLO_CACHE[key] = YOLO(key)
    return _YOLO_CACHE[key]


def _get_sahi_model(model_path: Path):
    key = str(model_path)
    if key not in _SAHI_CACHE:
        if not model_path.exists():
            raise FileNotFoundError(f"SAHI model weights not found: {model_path}")
        # Imported lazily so the plain-YOLO path works without sahi installed.
        from sahi import AutoDetectionModel

        _SAHI_CACHE[key] = AutoDetectionModel.from_pretrained(
            model_type=config.SAHI_MODEL_TYPE,
            model_path=key,
            confidence_threshold=config.SAHI_CONFIDENCE_THRESHOLD,
            device=config.SAHI_DEVICE,
        )
    return _SAHI_CACHE[key]


def _encode_jpg(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise ValueError("Failed to encode image.")
    return encoded.tobytes()


def _detect_with_yolo(image_bgr: np.ndarray, model_path: Path, conf_threshold: float, iou_threshold: float) -> list[_RawBox]:
    """Single full-frame YOLO pass (fallback path)."""
    model = _get_model(model_path)
    result = model.predict(image_bgr, conf=conf_threshold, iou=iou_threshold, verbose=False)[0]
    names = result.names or {}

    boxes: list[_RawBox] = []
    if result.boxes is not None:
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            class_id = int(box.cls[0].item()) if box.cls is not None else -1
            confidence = float(box.conf[0].item()) if box.conf is not None else 0.0
            boxes.append(
                _RawBox(x1, y1, x2, y2, confidence, class_id, names.get(class_id, str(class_id)))
            )
    return boxes


def _detect_with_sahi(image_bytes: bytes, model_path: Path) -> list[_RawBox]:
    """SAHI sliced inference (default path)."""
    from sahi.predict import get_sliced_prediction

    model = _get_sahi_model(model_path)
    pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    result = get_sliced_prediction(
        pil_image,
        model,
        slice_height=config.SAHI_SLICE_HEIGHT,
        slice_width=config.SAHI_SLICE_WIDTH,
        overlap_height_ratio=config.SAHI_OVERLAP_RATIO,
        overlap_width_ratio=config.SAHI_OVERLAP_RATIO,
        postprocess_type=config.SAHI_POSTPROCESS_TYPE,
        postprocess_match_metric=config.SAHI_MATCH_METRIC,
        postprocess_match_threshold=config.SAHI_MATCH_THRESHOLD,
        verbose=0,
    )

    boxes: list[_RawBox] = []
    for pred in result.object_prediction_list:
        x1, y1, x2, y2 = pred.bbox.to_xyxy()
        class_id = int(pred.category.id)
        class_name = pred.category.name or str(class_id)
        boxes.append(_RawBox(x1, y1, x2, y2, float(pred.score.value), class_id, class_name))
    return boxes


def _detect_with_detr_onnx(image_bgr: np.ndarray, info: dict) -> list[_RawBox]:
    """Whole-image pass of an RF-DETR style ONNX model at its own cut-off.

    The image is the already decoded (and EXIF-rotated) BGR array, so the boxes
    land in exactly the pixel space the crops are cut from.
    """
    detector = onnx_detector.get_detector(info)
    pil_image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
    return [
        _RawBox(b.x1, b.y1, b.x2, b.y2, b.score, b.class_id, b.class_name)
        for b in detector.predict(pil_image)
    ]


def _detect(image_bytes: bytes, image_bgr: np.ndarray, conf_threshold: float, iou_threshold: float) -> list[_RawBox]:
    """Run the active detection model. ``conf_threshold``/``iou_threshold`` apply
    to the plain YOLO pass only; SAHI and ONNX models use their own settings."""
    info = model_config.active_detection_info()
    if info["framework"] == model_config.DETR_ONNX_FRAMEWORK:
        return _detect_with_detr_onnx(image_bgr, info)
    det_path = info["weights"]
    if model_config.active_use_sahi():
        return _detect_with_sahi(image_bytes, det_path)
    return _detect_with_yolo(image_bgr, det_path, conf_threshold, iou_threshold)


def detect_and_crop_products(
    image_bytes: bytes,
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45,
) -> tuple[bytes, list[DetectionCrop]]:
    """Detect products and return the annotated image bytes and per-product crops."""

    if not image_bytes:
        raise ValueError("Empty input image.")

    np_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Invalid image format.")

    raw_boxes = _detect(image_bytes, image_bgr, conf_threshold, iou_threshold)

    height, width = image_bgr.shape[:2]
    crops: list[DetectionCrop] = []

    for raw in raw_boxes:
        x1 = max(0, min(int(raw.x1), width - 1))
        y1 = max(0, min(int(raw.y1), height - 1))
        x2 = max(0, min(int(raw.x2), width))
        y2 = max(0, min(int(raw.y2), height))

        if x2 - x1 < 5 or y2 - y1 < 5:
            continue

        crop_bgr = image_bgr[y1:y2, x1:x2]
        if crop_bgr.size == 0:
            continue

        crops.append(
            DetectionCrop(
                image_bytes=_encode_jpg(crop_bgr),
                bbox={
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "confidence": max(0.0, min(1.0, raw.confidence)),
                    "class_id": raw.class_id,
                    "class_name": raw.class_name,
                },
            )
        )

    # Only the confidence as the label: the class is always "product", and on
    # a dense shelf a longer label hid the products themselves.
    annotated_bgr = image_bgr.copy()
    _draw_labeled_boxes(
        annotated_bgr,
        [(c.bbox["x1"], c.bbox["y1"], c.bbox["x2"], c.bbox["y2"], f"{c.bbox['confidence']:.0%}") for c in crops],
    )
    annotated_bytes = _encode_jpg(annotated_bgr)
    return annotated_bytes, crops


def _draw_labeled_boxes(
    image_bgr: np.ndarray,
    boxes: list[tuple[int, int, int, int, str]],
    color: tuple[int, int, int] = (0, 255, 0),
) -> None:
    """Draw thin boxes with small labels, in place.

    Line width and text size follow the photo's size, so the overlay looks the
    same on screen for a small image and a 4k one: 2px lines on a typical 3-4k
    shelf photo (1px on small images), and labels that stay small next to the
    products instead of covering them.
    """
    height, width = image_bgr.shape[:2]
    long_side = max(width, height)
    line = max(1, round(long_side / 2000))
    font_scale = min(1.0, max(0.3, long_side / 5300))  # 0.3 at 1600px, 0.62 at 3264px
    font_weight = 2 if font_scale >= 0.6 else 1
    pad = max(2, round(font_scale * 5))
    for x1, y1, x2, y2, label in boxes:
        cv2.rectangle(image_bgr, (x1, y1), (x2, y2), color, line)
        text = str(label)
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_weight)
        cv2.rectangle(image_bgr, (x1, y1 - th - 2 * pad), (x1 + tw + 2 * pad, y1), color, -1)
        cv2.putText(image_bgr, text, (x1 + pad, y1 - pad),
                    cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 0), font_weight, cv2.LINE_AA)


def annotate_boxes(
    image_bytes: bytes,
    boxes: list[tuple[int, int, int, int, str]],
    color: tuple[int, int, int] = (0, 255, 0),
) -> bytes:
    """Draw labeled boxes on an image and return JPEG bytes.

    ``boxes`` is a list of ``(x1, y1, x2, y2, label)`` in absolute pixels. Used to
    render the "known products only" overlay on the original shelf image.
    """
    np_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Invalid image format.")

    _draw_labeled_boxes(image_bgr, boxes, color)
    return _encode_jpg(image_bgr)


def detect_products(
    image_bytes: bytes,
    conf_threshold: float | None = None,
) -> tuple[int, int, list[tuple[bytes, tuple[int, int, int, int]]]]:
    """Lean detection for the Data Dump pipeline.

    Honours the active model config (model type, SAHI on/off), skips annotation, and returns
    ``(width, height, [(crop_jpeg, (x1, y1, x2, y2)), ...])`` in absolute pixels.
    Nothing is written to disk.
    """
    if not image_bytes:
        raise ValueError("Empty input image.")

    np_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Invalid image format.")

    conf = config.DATA_DUMP_DETECTION_CONF if conf_threshold is None else conf_threshold
    raw_boxes = _detect(image_bytes, image_bgr, conf, 0.45)

    height, width = image_bgr.shape[:2]
    crops: list[tuple[bytes, tuple[int, int, int, int]]] = []
    for raw in raw_boxes:
        x1 = max(0, min(int(raw.x1), width - 1))
        y1 = max(0, min(int(raw.y1), height - 1))
        x2 = max(0, min(int(raw.x2), width))
        y2 = max(0, min(int(raw.y2), height))
        if x2 - x1 < 5 or y2 - y1 < 5:
            continue
        crop_bgr = image_bgr[y1:y2, x1:x2]
        if crop_bgr.size == 0:
            continue
        crops.append((_encode_jpg(crop_bgr), (x1, y1, x2, y2)))

    return width, height, crops
