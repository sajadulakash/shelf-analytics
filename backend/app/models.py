from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    model_id: str | None = None
    known_labels: list[str] = Field(default_factory=list)


class SyncToggle(BaseModel):
    enabled: bool


# ---------- Model Versions dashboard ----------
_Score = float | None

# Which metric columns belong to which model type. A score outside its type is
# rejected rather than silently stored, so "not applicable" always stays NULL.
DETECTION_ONLY_METRICS = ("map50", "map50_95")
CLASSIFICATION_ONLY_METRICS = ("accuracy",)


class ModelVersionIn(BaseModel):
    """One row of ``model_versions``. Scores are fractions 0-1 (94.3% = 0.943)."""

    # model_name / model_type are the table's column names, not pydantic internals.
    model_config = ConfigDict(protected_namespaces=())

    model_name: str = Field(min_length=1, max_length=100)
    model_type: Literal["detection", "classification"]
    version: str = Field(min_length=1, max_length=50)
    training_date: date | None = None
    dataset_name: str | None = Field(default=None, max_length=200)
    map50: _Score = Field(default=None, ge=0, le=1)
    map50_95: _Score = Field(default=None, ge=0, le=1)
    accuracy: _Score = Field(default=None, ge=0, le=1)
    precision: _Score = Field(default=None, ge=0, le=1)
    recall: _Score = Field(default=None, ge=0, le=1)
    f1_score: _Score = Field(default=None, ge=0, le=1)
    number_of_classes: int | None = Field(default=None, ge=0)
    change_summary: str | None = None
    model_artifact_uri: str | None = None
    notes: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_none(cls, value):
        # Form fields arrive as "" when left empty; store those as NULL.
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def _metrics_match_type(self):
        wrong = (
            CLASSIFICATION_ONLY_METRICS if self.model_type == "detection" else DETECTION_ONLY_METRICS
        )
        given = [name for name in wrong if getattr(self, name) is not None]
        if given:
            raise ValueError(
                f"{', '.join(given)} does not apply to a {self.model_type} model; leave it empty."
            )
        return self
