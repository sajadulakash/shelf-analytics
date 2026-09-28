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

# Model registry. Detection weights live in models/yolo/*.pt, classification
# models in models/swinv2/<name>/ (each a HF model dir with config.json).
MODELS_DIR = BASE_DIR / "models"
YOLO_DIR = MODELS_DIR / "yolo"
SWINV2_DIR = MODELS_DIR / "swinv2"

# Active model + label selection, chosen on the Model Configuration page and
# remembered here until reconfigured.
MODEL_CONFIG_FILE = DATA_DIR / "model_config.json"
# Cached content hashes of the model files, so the identity of a run can be
# derived without re-hashing hundreds of MB on every job.
MODEL_FINGERPRINT_FILE = DATA_DIR / "model_fingerprints.json"

# Legacy defaults / fallback paths.
YOLO_MODEL_PATH = YOLO_DIR / "best.pt"
SWINV2_MODEL_DIR = SWINV2_DIR / "swinv2_model"

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
# fragments back into one box, where plain NMS would leave both. Lower threshold
# merges more aggressively (fewer overlapping/duplicate boxes); higher keeps more
# separate. 0.2 clears duplicate overlaps on dense shelves while still keeping
# distinct neighbouring products apart.
SAHI_POSTPROCESS_TYPE = os.environ.get("SAHI_POSTPROCESS_TYPE", "GREEDYNMM")
SAHI_MATCH_METRIC = os.environ.get("SAHI_MATCH_METRIC", "IOS")
SAHI_MATCH_THRESHOLD = float(os.environ.get("SAHI_MATCH_THRESHOLD", "0.2"))

# Max concurrent crop classifications (Vision + Gemini calls)
CLASSIFICATION_CONCURRENCY = int(os.environ.get("CLASSIFICATION_CONCURRENCY", "3"))
SWINV2_CONFIDENCE_THRESHOLD = float(os.environ.get("SWINV2_CONFIDENCE_THRESHOLD", "0.88"))
# Device for the SwinV2 classifier (GPU by default, falls back to CPU only if
# CUDA is unavailable — checked at load time).
CLASSIFIER_DEVICE = os.environ.get("CLASSIFIER_DEVICE", "cuda:0")
UNKNOWN_PRODUCT_LABELS = {
    "unknown",
    "unknown product",
    "unknown-products",
    "unknown_product",
}

# ---------- Postgres (Database Data Dump) ----------
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "shelf_analytics_db")
DB_USER = os.environ.get("DB_USER", "postgres")
# Password comes from the environment / backend/.env (never hard-coded here).
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")

# ---------- Data Dump batch pipeline ----------
# CSV of (image_id, image_url) -> download -> detect -> classify -> Postgres.
# Downloads run concurrently and feed a bounded queue so slow/dead URLs never
# stall the GPU; the GPU processes one image at a time (classify in batches).
DATA_DUMP_DOWNLOAD_CONCURRENCY = int(os.environ.get("DATA_DUMP_DOWNLOAD_CONCURRENCY", "30"))
DATA_DUMP_QUEUE_MAX = int(os.environ.get("DATA_DUMP_QUEUE_MAX", "32"))
DATA_DUMP_CLASSIFY_BATCH = int(os.environ.get("DATA_DUMP_CLASSIFY_BATCH", "64"))
# httpx timeouts: connect is a hard cap; read is per-chunk inactivity, so a
# slow-but-steady download is never dropped — only a truly stalled one is.
DATA_DUMP_CONNECT_TIMEOUT = float(os.environ.get("DATA_DUMP_CONNECT_TIMEOUT", "10"))
DATA_DUMP_READ_TIMEOUT = float(os.environ.get("DATA_DUMP_READ_TIMEOUT", "30"))
# Retries for transient download failures (timeout / connection / 5xx); a clean
# 404 or a non-image body is never retried.
DATA_DUMP_RETRIES = int(os.environ.get("DATA_DUMP_RETRIES", "1"))
DATA_DUMP_DETECTION_CONF = float(os.environ.get("DATA_DUMP_DETECTION_CONF", "0.25"))
# A job cut off by a restart/crash is reopened on the next startup. With this on
# (the default) it also picks up again automatically from its first unfinished
# row; set to 0 to leave it paused for a manual Resume instead.
DATA_DUMP_AUTO_RESUME = _env_flag("DATA_DUMP_AUTO_RESUME", True)

# ---------- Sync to the remote product-sense database ----------
# Detections are written locally first, then pushed to the remote in the
# background. `synced_at` on product_detections is the watermark: NULL means the
# row has not been sent yet.
#
# The remote table is `market_intelligence_inference`. Its x1/y1/x2/y2 columns
# are misnamed -- they hold centre-x, centre-y, width, height, normalised 0-1,
# exactly like the local columns -- so the mapping is a straight copy. Verified
# against 8.72M live rows: every one of them is invalid as a corner box, none is
# invalid as centre+size.
SYNC_DB_HOST = os.environ.get("SYNC_DB_HOST", "product-sense-alpha.server.fringecore.sh")
SYNC_DB_PORT = int(os.environ.get("SYNC_DB_PORT", "5432"))
SYNC_DB_NAME = os.environ.get("SYNC_DB_NAME", "product-sense")
SYNC_DB_USER = os.environ.get("SYNC_DB_USER", "mi_user")
# Never hard-coded: without SYNC_DB_PASSWORD in backend/.env the sync cannot run
# at all, which doubles as a safety interlock.
SYNC_DB_PASSWORD = os.environ.get("SYNC_DB_PASSWORD", "")
SYNC_TABLE = os.environ.get("SYNC_TABLE", "market_intelligence_inference")

# How often a sync cycle runs, and how many rows go per round trip.
SYNC_INTERVAL_SECONDS = int(os.environ.get("SYNC_INTERVAL_SECONDS", "3600"))
SYNC_BATCH_SIZE = int(os.environ.get("SYNC_BATCH_SIZE", "5000"))
SYNC_CONNECT_TIMEOUT = int(os.environ.get("SYNC_CONNECT_TIMEOUT", "15"))
# How often the loop wakes to notice the toggle changing (not how often it syncs).
SYNC_POLL_SECONDS = int(os.environ.get("SYNC_POLL_SECONDS", "15"))
# The on/off flag lives in the database (app_settings), because the API and the
# standalone sync worker are separate processes. Ships disabled.

# Human-readable identity of the models that produced a row, written into
# product_detections.model_id and copied to the remote (where it is NOT NULL).
# Overridden per setup by "model_id" in data/model_config.json.
DEFAULT_MODEL_ID = os.environ.get("MODEL_ID", "model-001-yolo26m-v001-swinv2-v001")
