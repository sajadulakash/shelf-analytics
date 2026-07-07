# ShelfAnalytics – Backend

FastAPI service for product detection (YOLO) and classification (SwinV2).
This app is API-only; the UI lives in `../frontend`.

## Run

```bash
conda activate shelf-analytics
pip install -r requirements.txt
python run.py          # http://127.0.0.1:8000  (override with PORT / HOST env vars)
```

Interactive API docs: http://127.0.0.1:8000/docs

## Key endpoints

- `GET  /health` – liveness check
- `GET  /api/labels`, `PUT /api/labels` – configured classifier labels
- `GET  /api/confidence` – recent classification confidence log
- `GET  /api/task-shops`, `POST /api/analyze-shop`, `POST /api/task-report` – batch shop analysis
- `POST /detect-shelf` → `POST /classify-detected-crops` – manual two-step pipeline
- `POST /classify-products` – classify pre-cropped images
- `/uploads/*` – static access to generated crop/detection images

## Layout

- `app/` – FastAPI app (routes, YOLO detection, SwinV2 classifier, config, schemas)
- `models/` – model weights (`best.pt`, `swinv2_model/`), hosted on Hugging Face
- `shop-images/` – input images, one folder per shop
- `uploads/`, `results/`, `data/` – runtime-generated (git-ignored)

CORS is open (`*`) so the separate frontend can call it cross-origin.
