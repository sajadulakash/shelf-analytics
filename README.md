# ShelfAnalytics

ShelfAnalytics is a mudi shop shelf analysis project. It takes shop shelf images, detects visible products, classifies the detected product crops, and creates a product report that can help understand what SKUs are present in a shop image.

The current version uses a YOLO detection model and a local SwinV2 classification model. The detector performs well, but it can still miss some products. The classifier currently supports 31 labels, including one `Unknown` class. Later, more labels will be added so the system can cover all required SKUs.

## Quick Start

```bash
conda activate shelf-analytics
pip install -r requirements.txt
python run.py
```

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
├── app/
│   ├── main.py
│   ├── classifier.py
│   ├── detection_service.py
│   ├── config.py
│   └── models.py
├── assets/
│   └── screenshots used in README
├── models/                 # model files are hosted on Hugging Face
│   ├── best.pt
│   └── swinv2_model/
├── shop-images/
│   └── mudi shop input images
├── static/
│   ├── index.html
│   ├── process.html
│   ├── labels.html
│   └── con.html
├── uploads/                 # runtime generated files
│   ├── raw/
│   ├── detections/
│   └── cropped/
├── results/                 # runtime reports and logs
│   ├── runs/
│   └── classification_log.jsonl
├── requirements.txt
├── run.py
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
