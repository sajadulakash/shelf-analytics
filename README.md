# ShelfAnalytics

ShelfAnalytics is a mudi shop shelf analysis project. It takes shop shelf images, detects visible products, classifies the detected product crops, and creates a product report that can help understand what SKUs are present in a shop image.

Detection runs a YOLO model through **SAHI** (Slicing Aided Hyper Inference),
which tiles the high-resolution shelf image so small/edge products are not
missed, and classification uses a local **SwinV2** model. The classifier
currently supports 54 product labels; crops that fall below the confidence
threshold (or outside the requested label set) are reported as `Unknown`.

The project now runs like a single app in production: the FastAPI backend serves both the API and the static frontend from `frontend/`. The frontend can still be served separately with npm for development.

## Requirements

- Python 3.10+ (project uses the `shelf-a` conda env) for the backend.
- Node.js + npm only if you want to serve the frontend separately for development.
- An **NVIDIA GPU with CUDA** — SAHI detection runs on `cuda:0` by default.
- Model weights present under `backend/models/` (`best.pt` and `swinv2_model/`),
  hosted on Hugging Face and pulled separately (they are git-ignored).

## Quick Start

Run the backend; it serves both the frontend and API on the same port.

```bash
conda activate shelf-a
pip install -r requirements.txt
cd backend
python run.py                 # -> http://127.0.0.1:8000  (override with PORT=...)
```

Then open http://127.0.0.1:8000. Interactive API docs remain at http://127.0.0.1:8000/docs.

**Access from another PC on the LAN:** the backend binds `0.0.0.0`, so browse
to `http://<host-ip>:8000` from the other machine (e.g.
`http://192.168.68.64:8000`). Make sure the host firewall allows port `8000`.

**Optional frontend-only development server:**

```bash
cd frontend
npm install                   # once
npm start                     # -> http://127.0.0.1:3001
```

When opened from port `3001`, the frontend still calls the backend on port `8000`.

## Configuration

Backend behaviour is controlled by environment variables (see
`backend/app/config.py`). Common ones:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8000` | Port for the combined frontend/API server. |
| `HOST` | `0.0.0.0` | Backend bind address (LAN-reachable by default). |
| `USE_SAHI` | `1` | `1` = SAHI sliced detection, `0` = single full-frame `YOLO.predict`. |
| `SAHI_DEVICE` | `cuda:0` | Detection device (GPU). |
| `SAHI_MATCH_THRESHOLD` | `0.3` | Slice-merge threshold — lower merges split boxes more aggressively, higher keeps more separate. |
| `SAHI_CONFIDENCE_THRESHOLD` | `0.25` | Detection confidence cutoff. |
| `SWINV2_CONFIDENCE_THRESHOLD` | `0.99` | Below this a crop is reported as `Unknown`. |
| `CLASSIFICATION_CONCURRENCY` | `3` | Max concurrent crop classifications. |

The frontend has no build step. When served by FastAPI it uses same-origin API calls; when served separately on port `3001`, it falls back to `<page-host>:8000`.

## Features

- Detects products from mudi shop shelf images using YOLO + SAHI sliced inference.
- Merges slice-boundary fragments (GREEDYNMM) so tall/wide products are not double-counted.
- Crops detected products automatically.
- Classifies each crop with the local SwinV2 model.
- Marks uncertain or unsupported products as `Unknown`.
- Generates product count reports by shop.
- Supports task report and manual image processing flows.
- Keeps classification logs for confidence review.

## Project Structure

```text
ShelfAnalytics/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── classifier.py
│   │   ├── detection_service.py
│   │   ├── config.py
│   │   └── models.py
│   ├── models/                 # model files are hosted on Hugging Face
│   │   ├── best.pt
│   │   └── swinv2_model/
│   ├── shop-images/            # mudi shop input images
│   ├── uploads/                # runtime generated files (raw/detections/cropped)
│   ├── results/                # runtime reports and logs (runs/, classification_log.jsonl)
│   ├── data/                   # managed_labels.json (label overrides)
│   └── run.py
├── requirements.txt            # backend Python dependencies
├── frontend/
│   ├── index.html              # Get Task Report
│   ├── process.html            # Explore Process (step-by-step pipeline)
│   ├── labels.html             # Manage Labels (placeholder)
│   ├── con.html                # Confidence log viewer
│   ├── package.json            # optional npm start -> http-server on :3001
│   └── assets/
│       ├── css/                # app.css (shared), labels.css, con.css
│       └── js/                 # config.js, index.js, process.js, con.js, vendor/
├── assets/                     # screenshots used in this README
└── README.md
```

## Project Flow

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

- Detection uses the YOLO model from `models/best.pt`, run through SAHI sliced
  inference by default (set `USE_SAHI=0` to fall back to a single full-frame pass).
- Classification uses the SwinV2 model from `models/swinv2_model`.
- Current classifier supports 54 product labels; low-confidence or out-of-set
  crops are reported as `Unknown`.
- Future goal: expand labels until all target SKUs are covered.
