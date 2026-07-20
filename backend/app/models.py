from __future__ import annotations
from pydantic import BaseModel, Field


# ---------- Per-image result ----------
class ImageClassificationResult(BaseModel):
    filename: str
    predicted_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    is_unknown: bool = False
    reason: str | None = None
    ocr_text: str = ""
    vision_labels: list[str] = []


# ---------- Aggregated response ----------
class ClassificationResponse(BaseModel):
    total_images: int
    results: list[ImageClassificationResult]
    label_counts: dict[str, int]
    unknown_count: int


# ---------- Stored debug record ----------
class ClassificationRecord(BaseModel):
    filename: str
    image_path: str
    ocr_text: str
    vision_labels: list[str]
    predicted_label: str
    confidence: float
    is_unknown: bool
    reason: str | None = None


class DetectionBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float = Field(ge=0.0, le=1.0)
    class_id: int
    class_name: str


class CropClassificationResult(BaseModel):
    crop_filename: str
    crop_url: str
    crop_image_b64: str = ""  # base64-encoded JPEG
    bbox: DetectionBox
    predicted_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    is_unknown: bool = False
    reason: str | None = None


class DetectedCrop(BaseModel):
    crop_filename: str
    crop_url: str
    crop_image_b64: str = ""  # base64-encoded JPEG
    bbox: DetectionBox


class ShelfDetectionResponse(BaseModel):
    run_id: str
    raw_filename: str
    detection_image_url: str
    detection_image_b64: str = ""  # base64-encoded JPEG
    total_detections: int
    crops: list[DetectedCrop]
    existing_labels: list[str]


class ShelfClassificationResponse(BaseModel):
    run_id: str
    total_detections: int
    classifications: list[CropClassificationResult]
    label_counts: dict[str, int]
    unknown_count: int
    existing_labels: list[str]
    missing_labels: list[str]
    known_overlay_b64: str = ""  # original image with only known products boxed


class ShopTaskInput(BaseModel):
    shop_name: str
    image_count: int


class ShopTaskListResponse(BaseModel):
    image_root: str
    shops: list[ShopTaskInput]


class ShopReportRow(BaseModel):
    shop_name: str
    image_count: int
    total_detections: int
    product_counts: dict[str, int]
    unknown_count: int
    existing_labels: list[str]
    missing_labels: list[str]
    errors: list[str] = Field(default_factory=list)


class ShopTaskReportResponse(BaseModel):
    image_root: str
    shops: list[ShopReportRow]
    labels: list[str]
    totals: dict[str, int]
    unknown_count: int


class DetectionClassificationResponse(BaseModel):
    raw_filename: str
    detection_image_url: str
    total_detections: int
    crops: list[CropClassificationResult]
    label_counts: dict[str, int]
    unknown_count: int
    existing_labels: list[str]
    missing_labels: list[str]


class LabelSettingsResponse(BaseModel):
    labels: list[str]
    default_labels: list[str]


class LabelSettingsUpdate(BaseModel):
    labels: list[str]


class ModelConfigUpdate(BaseModel):
    detection_model: str | None = None
    classification_model: str | None = None
    use_sahi: bool | None = None
    known_labels: list[str] = Field(default_factory=list)
