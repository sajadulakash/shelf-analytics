# ShelfAnalytics

ShelfAnalytics is a mudi shop shelf analysis project. It takes shop shelf images, detects visible products, classifies the detected product crops, and creates a product report that can help understand what SKUs are present in a shop image.

Detection runs a YOLO model through **SAHI** (Slicing Aided Hyper Inference),
which tiles the high-resolution shelf image so small/edge products are not
missed, and classification uses a local **SwinV2** model. Crops that fall below
the confidence threshold (or outside the configured *known* label set) are
reported as `Unknown`.

The project runs as two processes: a **FastAPI backend** (API only) and a
**React + Vite frontend**. The frontend calls the backend through the Vite dev
proxy, so both sides are same-origin during development.

## Requirements

- Python 3.10+ (project uses the `shelf-a` conda env) for the backend.
- Node.js + npm for the frontend.
- An **NVIDIA GPU with CUDA** — detection and classification default to `cuda:0`.
- Model weights under `backend/models/` (`yolo/best.pt` and `swinv2/<model>/`),
  hosted on Hugging Face and pulled separately (they are git-ignored).
- PostgreSQL — only for the **Database Data Dump** page.

## Quick Start

Run the backend and the frontend in two terminals.

**Terminal 1 — backend (API, port 8000):**

```bash
conda activate shelf-a
pip install -r requirements.txt
cd backend
python run.py                 # -> http://127.0.0.1:8000  (override with PORT=...)
```

**Terminal 2 — frontend (UI, port 5173):**

```bash
cd frontend
npm install                   # once
npm run dev                   # -> http://localhost:5173
```

> There is **no `npm start`** script. Use `npm run dev` (or `npm run build` /
> `npm run preview`).

Then open http://localhost:5173. Interactive API docs are at
http://127.0.0.1:8000/docs.

**Access from another PC on the LAN:** the backend binds `0.0.0.0` and Vite runs
with `host: true`, so both are reachable from another machine (e.g.
`http://192.168.68.64:5173`). Make sure the host firewall allows ports `5173`
and `8000`. If the backend is on a different host than the dev server, point the
proxy at it:

```bash
VITE_BACKEND=http://192.168.68.64:8000 npm run dev
```

**Production build:**

```bash
cd frontend
npm run build                 # -> frontend/dist/
npm run preview               # preview the built app
```

Serve `dist/` from any static host. When the built app is served from a
different origin than the API, set the API base at build time:

```bash
VITE_API_BASE=http://192.168.68.64:8000 npm run build
```

## Pages

| Page | Route | What it does |
| --- | --- | --- |
| **Model Configuration** | `/models` | Pick the YOLO weights and SwinV2 classifier, toggle SAHI on/off, and check which labels count as *known*. Saved to `backend/data/model_config.json` and used by every pipeline run. |
| **Explore Process** | `/` | Upload one shelf image → detect → classify each crop → report. Shows the annotated image, every classified crop (click to enlarge), a known-products-only overlay, and label counts. |
| **Database Data Dump** | `/data-dump` | Upload a CSV of `image_id, image_url`; the backend downloads each image, runs detect + classify, and writes rows to Postgres. Live progress, counts, cancel, and per-image failures. |
| **Confidence** | `/confidence` | Recent classification confidence log, read from `backend/results/classification_log.jsonl`. |

## Configuration

### Backend

Backend behaviour is controlled by environment variables (see
`backend/app/config.py`). Secrets go in `backend/.env` (git-ignored).

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8000` | Backend API port. |
| `HOST` | `0.0.0.0` | Backend bind address (LAN-reachable by default). |
| `SHOP_IMAGES_DIR` | `backend/shop-images` | Root for the batch task-report flow (one folder per shop). |
| `USE_SAHI` | `1` | Default detection mode. Once saved on the Model Configuration page, `data/model_config.json` wins. |
| `SAHI_DEVICE` | `cuda:0` | Detection device (GPU). |
| `SAHI_SLICE_WIDTH` / `SAHI_SLICE_HEIGHT` | `640` | Slice size for sliced inference. |
| `SAHI_OVERLAP_RATIO` | `0.2` | Slice overlap. |
| `SAHI_CONFIDENCE_THRESHOLD` | `0.25` | Detection confidence cutoff. |
| `SAHI_POSTPROCESS_TYPE` | `GREEDYNMM` | Slice-merge algorithm. |
| `SAHI_MATCH_METRIC` | `IOS` | Merge metric (intersection-over-smaller). |
| `SAHI_MATCH_THRESHOLD` | `0.2` | Slice-merge threshold — lower merges split boxes more aggressively, higher keeps more separate. |
| `SWINV2_CONFIDENCE_THRESHOLD` | `0.88` | Below this a crop is reported as `Unknown`. |
| `CLASSIFIER_DEVICE` | `cuda:0` | Classifier device (falls back to CPU if CUDA is unavailable). |
| `CLASSIFICATION_CONCURRENCY` | `3` | Max concurrent crop classifications. |

**Postgres (Database Data Dump only):**

| Variable | Default |
| --- | --- |
| `DB_HOST` | `localhost` |
| `DB_PORT` | `5432` |
| `DB_NAME` | `shelf_analytics_db` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | *(empty — set it in `backend/.env`)* |

**Data Dump tuning:** `DATA_DUMP_DOWNLOAD_CONCURRENCY` (`30`),
`DATA_DUMP_QUEUE_MAX` (`32`), `DATA_DUMP_CLASSIFY_BATCH` (`64`),
`DATA_DUMP_CONNECT_TIMEOUT` (`10`), `DATA_DUMP_READ_TIMEOUT` (`30`),
`DATA_DUMP_RETRIES` (`1`), `DATA_DUMP_MAX_FAILURES_TRACKED` (`200`),
`DATA_DUMP_DETECTION_CONF` (`0.25`).

The dump writes to a `product_detections` table that must already exist —
bbox values are normalised (0–1) relative to the source image:

```sql
CREATE TABLE product_detections (
    image_id    TEXT,
    class_name  TEXT,
    x_center    DOUBLE PRECISION,
    y_center    DOUBLE PRECISION,
    bbox_width  DOUBLE PRECISION,
    bbox_height DOUBLE PRECISION
);
```

### Frontend

| Variable | When | Purpose |
| --- | --- | --- |
| `VITE_BACKEND` | dev | Target for the Vite proxy (default `http://localhost:8000`). |
| `VITE_API_BASE` | build | API origin baked into the build, when `dist/` is served separately from the API. |

## Features

- Detects products from mudi shop shelf images using YOLO, with optional SAHI sliced inference.
- Merges slice-boundary fragments (GREEDYNMM + IOS) so tall/wide products are not double-counted.
- Crops detected products automatically and classifies each crop with the local SwinV2 model.
- Marks uncertain or unsupported products as `Unknown`.
- Swappable models: drop new weights into `models/yolo/` or `models/swinv2/` and pick them in the UI.
- Per-label *known* selection — anything unchecked is reported as `Unknown`.
- Known-products-only overlay on the original shelf image.
- Generates product count reports by shop (batch API over `shop-images/`).
- Bulk CSV → Postgres dump pipeline with live progress and failure reporting.
- Keeps classification logs for confidence review.

## API

Browse `/docs` for the full interactive list. Main routes:

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/detect-shelf` | Upload a shelf image → annotated image + crops + `run_id`. |
| `POST` | `/classify-detected-crops` | Classify a run's crops → labels, counts, known overlay. |
| `POST` | `/classify-products` | Classify already-cropped product images directly. |
| `GET` | `/api/model-config` · `POST` `/api/model-config` | Read / save the active models, SAHI mode, and known labels. |
| `GET` | `/api/model-labels?classifier=` | Label list for a given classifier. |
| `GET` | `/api/labels` | Currently active (known) labels. |
| `GET` | `/api/task-shops` | Shop folders found under `SHOP_IMAGES_DIR`. |
| `POST` | `/api/analyze-shop` · `/api/task-report` | Batch report for one shop / every shop. |
| `POST` | `/api/data-dump` | Start a CSV → Postgres dump job. |
| `GET` | `/api/data-dump` · `/api/data-dump/{job_id}` | List jobs / poll one job. |
| `POST` | `/api/data-dump/{job_id}/cancel` | Request cancellation. |
| `GET` | `/api/confidence?limit=` | Recent classification confidence records. |
| `GET` | `/health` | Health check. |

## Project Structure

```text
ShelfAnalytics/
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI routes (API only)
│   │   ├── detection_service.py# YOLO / SAHI detection + cropping
│   │   ├── classifier.py       # SwinV2 classification
│   │   ├── model_config.py     # model registry + active selection
│   │   ├── data_dump.py        # CSV -> download -> detect -> classify -> Postgres
│   │   ├── db.py               # psycopg2 access layer
│   │   ├── config.py           # paths + env configuration
│   │   └── models.py           # pydantic request/response models
│   ├── models/                 # model files are hosted on Hugging Face
│   │   ├── yolo/best.pt
│   │   └── swinv2/<model>/     # HF model dirs (config.json, model.safetensors, …)
│   ├── shop-images/            # mudi shop input images (one folder per shop)
│   ├── uploads/                # runtime generated files (raw/detections/cropped)
│   ├── results/                # runtime reports and logs (runs/, classification_log.jsonl)
│   ├── data/                   # model_config.json (active models + known labels)
│   ├── .env                    # DB_PASSWORD and other secrets (git-ignored)
│   └── run.py
├── requirements.txt            # backend Python dependencies
├── frontend/                   # React 18 + Vite 6 + Tailwind 4
│   ├── src/
│   │   ├── main.jsx            # entry + router
│   │   ├── App.jsx             # layout + routes
│   │   ├── api.js              # backend calls
│   │   ├── index.css           # theme tokens
│   │   ├── components/         # Sidebar, UI primitives
│   │   └── pages/              # ExploreProcess, ModelConfig, DataDump, Confidence
│   ├── index.html
│   ├── vite.config.js          # dev proxy to the backend
│   └── package.json            # dev / build / preview
├── assets/                     # screenshots used in this README
└── README.md
```

## Project Flow

> The screenshots below were captured on an earlier build of the UI; the flow is
> the same, but the current React interface looks different.

### Landing Page

![Landing page](<assets/1. landing-page.png>)

### Task Report

![Task report](<assets/2. task-report.png>)

### Manual Process Page

![Explore process](<assets/3. explore-process.png>)

### Detected Products

![Detected products](<assets/4. detected-products.png>)

### Cropped Product Images

![Cropped product images](<assets/5. cropped-product-images.png>)

### Classified Products

![Classified products](<assets/classified-products.png>)

### Classification Report

![Classification report](<assets/classification-report.png>)

## Project Status

- Detection uses the YOLO weights selected on the Model Configuration page
  (`models/yolo/*.pt`), run either through SAHI sliced inference or a single
  full-frame pass.
- Classification uses the SwinV2 model selected on the same page
  (`models/swinv2/<model>/`). The current active model carries 55 classes
  (54 products + an `unknown` bucket).
- Low-confidence, out-of-set, or `unknown*` crops are reported as `Unknown`.
- Future goal: expand labels until all target SKUs are covered.
