"""YOLO-based product detection and crop extraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from ultralytics import YOLO

from app import config


@dataclass
class DetectionCrop:
    image_bytes: bytes
    bbox: dict[str, Any]


_MODEL: YOLO | None = None


def _get_model() -> YOLO:
    global _MODEL
    if _MODEL is None:
        if not config.YOLO_MODEL_PATH.exists():
            raise FileNotFoundError(f"YOLO model not found: {config.YOLO_MODEL_PATH}")
        _MODEL = YOLO(str(config.YOLO_MODEL_PATH))
    return _MODEL


def _encode_jpg(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise ValueError("Failed to encode image.")
    return encoded.tobytes()


def detect_and_crop_products(
    image_bytes: bytes,
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45,
) -> tuple[bytes, list[DetectionCrop]]:
    """Run YOLO detection and return annotated image bytes and crop bytes."""

    if not image_bytes:
        raise ValueError("Empty input image.")

    np_buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise ValueError("Invalid image format.")

    model = _get_model()
    result = model.predict(image_bgr, conf=conf_threshold, iou=iou_threshold, verbose=False)[0]

    crops: list[DetectionCrop] = []
    names = result.names or {}

    if result.boxes is not None:
        height, width = image_bgr.shape[:2]
        for box in result.boxes:
            xyxy = box.xyxy[0].tolist()
            x1, y1, x2, y2 = [int(v) for v in xyxy]
            x1 = max(0, min(x1, width - 1))
            y1 = max(0, min(y1, height - 1))
            x2 = max(0, min(x2, width))
            y2 = max(0, min(y2, height))

            if x2 - x1 < 5 or y2 - y1 < 5:
                continue

            crop_bgr = image_bgr[y1:y2, x1:x2]
            if crop_bgr.size == 0:
                continue

            class_id = int(box.cls[0].item()) if box.cls is not None else -1
            class_name = names.get(class_id, str(class_id))
            confidence = float(box.conf[0].item()) if box.conf is not None else 0.0

            crops.append(
                DetectionCrop(
                    image_bytes=_encode_jpg(crop_bgr),
                    bbox={
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "confidence": max(0.0, min(1.0, confidence)),
                        "class_id": class_id,
                        "class_name": class_name,
                    },
                )
            )

    # Draw green bounding boxes with OpenCV instead of YOLO default colours
    annotated_bgr = image_bgr.copy()
    green = (0, 255, 0)
    for crop in crops:
        b = crop.bbox
        cv2.rectangle(annotated_bgr, (b["x1"], b["y1"]), (b["x2"], b["y2"]), green, 3)
        label_text = f"{b['class_name']} {b['confidence']:.0%}"
        (tw, th), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(annotated_bgr, (b["x1"], b["y1"] - th - 8), (b["x1"] + tw + 4, b["y1"]), green, -1)
        cv2.putText(annotated_bgr, label_text, (b["x1"] + 2, b["y1"] - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2, cv2.LINE_AA)
    annotated_bytes = _encode_jpg(annotated_bgr)
    return annotated_bytes, crops
