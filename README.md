# ShelfAnalytics

ShelfAnalytics is a mudi shop shelf analysis project. It takes shop shelf images, detects visible products, classifies the detected product crops, and creates a product report that can help understand what SKUs are present in a shop image.

The current version uses a YOLO detection model and a local SwinV2 classification model. The detector performs well, but it can still miss some products. The classifier currently supports 31 labels, including one `Unknown` class. Later, more labels will be added so the system can cover all required SKUs.

The project is split into two independently run apps:

- **`backend/`** – a FastAPI service that exposes the detection/classification API.
- **`frontend/`** – a static HTML/CSS/JS app that talks to the backend over HTTP.

## Quick Start

Run the two apps in separate terminals.

**1. Backend (API)** — serves on a fixed port so the frontend has a stable target.

```bash
cd backend
conda activate shelf-analytics
pip install -r requirements.txt
python run.py                 # -> http://127.0.0.1:8000  (override with PORT=...)
```

**2. Frontend (static app)** — any static file server works.

```bash
cd frontend
python -m http.server 3000    # -> http://127.0.0.1:3000
```

Then open http://127.0.0.1:3000. If the backend runs somewhere other than
`http://127.0.0.1:8000`, edit `frontend/assets/js/config.js` and set
`window.API_BASE` to the backend URL. CORS is already open on the backend.

## Features

- Detects products from mudi shop shelf images using YOLO.
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
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── index.html              # Get Task Report
│   ├── process.html            # Explore Process (step-by-step pipeline)
│   ├── labels.html             # Manage Labels (placeholder)
│   ├── con.html                # Confidence log viewer
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

- Detection uses the YOLO model from `models/best.pt`.
- Classification uses the SwinV2 model from `models/swinv2_model`.
- Current classifier supports 31 labels, including `Unknown`.
- Future goal: expand labels until all target SKUs are covered.
