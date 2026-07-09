import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BASE_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
load_dotenv(BASE_DIR / ".env")

# Storage
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

UPLOAD_DIR = BASE_DIR / "uploads" / "cropped"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_DIR = BASE_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

RUNS_DIR = RESULTS_DIR / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

RAW_UPLOAD_DIR = BASE_DIR / "uploads" / "raw"
RAW_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DETECTION_DIR = BASE_DIR / "uploads" / "detections"
DETECTION_DIR.mkdir(parents=True, exist_ok=True)

MANAGED_LABELS_FILE = DATA_DIR / "managed_labels.json"

# Batch task input. Add one folder per shop under this directory, for example:
# shop-images/ma-mudi-dokan/*.jpg
# shop-images/bismillah-shop/*.jpg
SHOP_IMAGES_DIR = Path(os.environ.get("SHOP_IMAGES_DIR", BASE_DIR / "shop-images"))
SHOP_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

YOLO_MODEL_PATH = BASE_DIR / "models" / "best.pt"
SWINV2_MODEL_DIR = BASE_DIR / "models" / "swinv2_model"

# ---------- Detection: SAHI sliced inference ----------
# The detector runs SAHI (Slicing Aided Hyper Inference) by default, which
# tiles the high-resolution shelf image and merges predictions – it finds far
# more products on large images than a single full-frame pass. Set USE_SAHI=0
# to fall back to plain YOLO.predict.
def _env_flag(name: str, default: bool) -> bool:
    return os.environ.get(name, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}


USE_SAHI = _env_flag("USE_SAHI", True)
# Ultralytics weights loaded through SAHI's AutoDetectionModel.
SAHI_MODEL_PATH = Path(os.environ.get("SAHI_MODEL_PATH", YOLO_MODEL_PATH))
SAHI_MODEL_TYPE = os.environ.get("SAHI_MODEL_TYPE", "ultralytics")
# GPU by default (device is honoured as-is; no silent CPU fallback).
SAHI_DEVICE = os.environ.get("SAHI_DEVICE", "cuda:0")
SAHI_SLICE_WIDTH = int(os.environ.get("SAHI_SLICE_WIDTH", "640"))
SAHI_SLICE_HEIGHT = int(os.environ.get("SAHI_SLICE_HEIGHT", "640"))
SAHI_OVERLAP_RATIO = float(os.environ.get("SAHI_OVERLAP_RATIO", "0.2"))
SAHI_CONFIDENCE_THRESHOLD = float(os.environ.get("SAHI_CONFIDENCE_THRESHOLD", "0.25"))
# Slice-boundary merge. A product taller/wider than a slice is split across
# tiles; GREEDYNMM with the IOS (intersection-over-smaller) metric merges those
# fragments back into one box, where plain NMS would leave both. Threshold 0.3
# merges the split halves without fusing distinct neighbouring products.
SAHI_POSTPROCESS_TYPE = os.environ.get("SAHI_POSTPROCESS_TYPE", "GREEDYNMM")
SAHI_MATCH_METRIC = os.environ.get("SAHI_MATCH_METRIC", "IOS")
SAHI_MATCH_THRESHOLD = float(os.environ.get("SAHI_MATCH_THRESHOLD", "0.3"))

# Max concurrent crop classifications (Vision + Gemini calls)
CLASSIFICATION_CONCURRENCY = int(os.environ.get("CLASSIFICATION_CONCURRENCY", "3"))
SWINV2_CONFIDENCE_THRESHOLD = float(os.environ.get("SWINV2_CONFIDENCE_THRESHOLD", "0.99"))
UNKNOWN_PRODUCT_LABELS = {
    "unknown",
    "unknown product",
    "unknown-products",
    "unknown_product",
}
