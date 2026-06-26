import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
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

# Max concurrent crop classifications (Vision + Gemini calls)
CLASSIFICATION_CONCURRENCY = int(os.environ.get("CLASSIFICATION_CONCURRENCY", "3"))
SWINV2_CONFIDENCE_THRESHOLD = float(os.environ.get("SWINV2_CONFIDENCE_THRESHOLD", "0.99"))
UNKNOWN_PRODUCT_LABELS = {
    "unknown",
    "unknown product",
    "unknown-products",
    "unknown_product",
}
