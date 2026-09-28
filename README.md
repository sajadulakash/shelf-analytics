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

## Setup on a new machine

Needs Python 3.10+, Node.js, PostgreSQL, and an **NVIDIA GPU with CUDA**
(detection and classification default to `cuda:0`).

**1. Database**

```bash
createdb -h localhost -U postgres shelf_analytics_db
psql -h localhost -U postgres -d shelf_analytics_db -v ON_ERROR_STOP=1 -f schema.sql
```

**2. Secrets** — copy `backend/.env.example` to `backend/.env` and fill it in.
`SYNC_DB_PASSWORD` is only needed if you want the remote sync.

```bash
cp backend/.env.example backend/.env
```

**3. Model weights** — not in git. Pull them from Hugging Face into:

```
backend/models/yolo/best.pt
backend/models/swinv2/<model>/     # config.json, model.safetensors, preprocessor_config.json
```

**4. Backend** (port 8000). The `+cu121` torch wheels come from PyTorch's index,
which `requirements.txt` already points at.

```bash
pip install -r requirements.txt
cd backend && python run.py
```

**5. Frontend** (port 5173).

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. API docs at http://127.0.0.1:8000/docs.

**Optional — remote sync** (its own process, see [Syncing](#syncing-to-the-remote-database)):

```bash
cd backend && python sync_worker.py
```

## Notes

Hot-reload is off by default, since a reload kills a running data dump — use
`RELOAD=1 python run.py` while editing. There is no `npm start`; use
`npm run dev`, `npm run build` or `npm run preview`.

Both sides bind all interfaces, so another PC on the LAN can reach
`http://<host-ip>:5173` if the firewall allows it. If the backend is on a
different host, start the frontend with
`VITE_BACKEND=http://<host-ip>:8000 npm run dev`.

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
| **Database Data Dump** | `/data-dump` | Upload a CSV of `image_id, image_url`; the backend downloads each image, runs detect + classify, and writes rows to Postgres. Live progress, counts and cancel. Runs survive reloads and restarts — see [Durable dump jobs](#durable-dump-jobs). |
| **Runtime** | `/runtime` | Live feed of what the pipeline is doing — the last 10/15/25/50/100 images to be **dumped**, **skipped** or **failed**, the active job's progress, and the model setup in use. Refreshes every 2s. |

## Configuration

### Backend

Backend behaviour is controlled by environment variables (see
`backend/app/config.py`). Secrets go in `backend/.env` (git-ignored).

| Variable | Default | Purpose |
| --- | --- | --- |
| `PORT` | `8000` | Backend API port. |
| `HOST` | `0.0.0.0` | Backend bind address (LAN-reachable by default). |
| `RELOAD` | `0` | Uvicorn hot-reload. Leave off outside development — a reload kills running dump jobs. |
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
`DATA_DUMP_RETRIES` (`1`), `DATA_DUMP_DETECTION_CONF` (`0.25`),
`DATA_DUMP_AUTO_RESUME` (`1`).

### Skipping images that are already done

An image is re-inferred only when it has to be. Before a job starts, one
set-based statement marks every row whose image has already been processed
**under the exact same setup** as `skipped`; those images are never downloaded,
never hit the GPU, and their existing rows are left alone.

"The same setup" is a `config_key` — a hash of what actually determines the
output:

- the **contents** of the detection weights and the classifier directory (a
  sha256, cached against size+mtime, so retraining and overwriting `best.pt`
  produces a new key instead of silently serving stale labels),
- `use_sahi` and, when slicing is on, the slice/overlap/merge settings,
- the detection confidence and `SWINV2_CONFIDENCE_THRESHOLD`,
- the selected known-label set.

Change any of them and previously processed images stop matching, so they are
re-inferred rather than wrongly skipped.

The lookup is a table of its own, `image_inference_runs`, holding one row per
(image, config). It is deliberately *not* `product_detections`: that table
averages ~228 rows per image, so asking "has this been done?" there would mean
searching something two orders of magnitude larger than the question needs. The
check is a primary-key probe, so it stays fast as the ledger grows — going from
20 lakh to 1 crore rows costs roughly one extra page read — and it runs once per
job as a single join, never once per image.

The ledger row is written in the same transaction as the image's detections, so
it can never claim an image is done when its rows were rolled back.

### Syncing to the remote database

Detections are written locally first and pushed to the remote `product-sense`
database in the background. `product_detections.synced_at` is the whole
protocol: NULL means "not sent yet", so an interrupted cycle costs nothing but a
repeat of the batch that was in flight.

The sync is a **separate process** from the API, so it keeps working whether or
not the API is up and regardless of whether any inference is running. It talks
straight to the database and only ever looks at rows whose `synced_at` is NULL.

```bash
cd backend
python sync_worker.py          # run forever, a cycle every SYNC_INTERVAL_SECONDS
python sync_worker.py --once   # one cycle then exit (for cron)
python sync_worker.py --force  # ignore the on/off toggle for this run
```

`sync_worker.py`'s docstring carries a ready-made systemd unit and a cron line.

It is **off by default**. The toggle on the Database Data Dump page writes to
`app_settings.sync_enabled` in the database — not a file — so the API and the
worker agree even though they are different processes. The worker also refuses
to run unless `SYNC_DB_PASSWORD` is set in `backend/.env`, which doubles as a
safety interlock.

**Instant sync** next to the toggle pushes everything pending straight away,
whether or not the schedule is on. Because the API and the worker are separate
processes, a cycle holds a Postgres session-level advisory lock for its
duration — so a manual run and a scheduled one can never claim the same rows and
push them twice. Whichever asks second is refused (`409`) and simply waits for
the next tick; the lock is released automatically if a process is killed.

**The remote's column names are misleading.** `market_intelligence_inference`
has `x1, y1, x2, y2`, but those columns hold **centre-x, centre-y, width and
height**, normalised 0–1 — the same format as the local columns. Verified
against all 8.72M live rows: every one but 34,522 is invalid read as a corner
box, none is invalid read as centre+size, and `min(x1) * 2 == min(x2)` exactly
(a box touching the edge has centre = width/2). The copy is therefore 1:1 and no
geometry conversion is applied.

| local `product_detections` | remote `market_intelligence_inference` |
| --- | --- |
| `id` | `id` |
| `image_id` | `image_id` |
| `class_name` | `class_label` |
| `x_center` | `x1` |
| `y_center` | `y1` |
| `bbox_width` | `x2` |
| `bbox_height` | `y2` |
| `model_id` | `model_id` |
| `synced_at` | *(local only)* |

Rows without an `id` or a `model_id` are never sent — the remote requires
`model_id`, and the id is what makes a re-send safe. They are reported as
**blocked** in the sync panel until backfilled.

### Model registry

`model_id` is not a free-text setting: it comes from the `model_registry` table,
which maps each unique inference setup to exactly one id.

| column | meaning |
| --- | --- |
| `config_key` | derived identity of the setup (model file hashes, SAHI mode, thresholds, label selection) |
| `model_id` | the name written onto every detection row and carried to the remote |
| `detection_model`, `classification_model`, `use_sahi`, … | what that setup was, for reference |

A setup registers itself the first time it is used. The first one ever
registered inherits the existing `model-001-yolo26m-v001-swinv2-v001` name so
history stays continuous; later ones are numbered from it
(`model-002-…`). Because the key is derived rather than typed, swapping a model
or changing a threshold produces a new `model_id` automatically instead of
silently reusing the old one. `GET /api/models` lists them.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SYNC_DB_PASSWORD` | *(empty)* | Required. Without it the sync cannot be enabled. |
| `SYNC_DB_HOST` | `product-sense-alpha.server.fringecore.sh` | Remote host. |
| `SYNC_DB_NAME` | `product-sense` | Remote database. |
| `SYNC_DB_USER` | `mi_user` | Remote user. |
| `SYNC_TABLE` | `market_intelligence_inference` | Destination table. |
| `SYNC_INTERVAL_SECONDS` | `3600` | How often a cycle runs. |
| `SYNC_BATCH_SIZE` | `5000` | Rows per round trip. |
| `MODEL_ID` | `model-001-yolo26m-v001-swinv2-v001` | Name given to the first setup registered in `model_registry`. |
| `SYNC_POLL_SECONDS` | `15` | How often the worker notices the toggle changing. |

### Durable dump jobs

A dump run is not held in memory, so **closing the tab, reloading the browser,
restarting the server or losing power does not lose the run**:

- The job and every CSV row are written to Postgres *before* the upload request
  returns, so the work queue exists on disk from the start.
- Each image's detections and its "done" mark commit in the **same transaction**,
  so a crash can never leave rows in the database with the image still pending —
  which on resume would duplicate every row for that image.
- On startup, any job still marked `queued`/`running` is reopened as
  `interrupted` and resumed from its first unfinished row. Set
  `DATA_DUMP_AUTO_RESUME=0` to leave it paused for a manual **Resume** instead.
- The Data Dump page re-attaches to a live or interrupted job when it loads, and
  lists recent runs so any of them can be reopened or resumed.

Worst case you lose the single image that was mid-GPU when the power went — it
goes back to pending and is redone on resume.

Three tables are used, all created automatically at startup if missing
(`db.ensure_schema`). `product_detections` holds the output, with bbox values
normalised (0–1) relative to the source image; `data_dump_jobs` and
`data_dump_items` hold the resumable job state:

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

### Maintenance

Two jobs are too heavy for startup on an existing `product_detections` table and
are run by hand:

```bash
cd backend
python -m app.maintenance ledger-status      # ledger coverage + active config key
python -m app.maintenance sync-status        # remote sync backlog
python -m app.maintenance prepare-sync       # backfill row ids on existing rows
python -m app.maintenance create-indexes     # product_detections indexes, CONCURRENTLY
python -m app.maintenance backfill-ledger --config-key <key>
```

`prepare-sync` gives every pre-existing row the `id` the sync needs (add
`--model-id <id>` to fill `model_id` too). It walks the table in page ranges and
commits each batch, so it can be stopped and restarted and only ever touches
rows that are still NULL. New rows written by the pipeline already have both.

`create-indexes` builds the `image_id` index that per-image lookups need;
without it they are a full scan of the whole table. It runs `CONCURRENTLY`, so
reads and writes keep working while it builds.

`backfill-ledger` registers images already in `product_detections` so they are
skipped in future. It takes the config key explicitly on purpose: registering
old rows under the *current* key when they came from an older model would make
the pipeline skip images that ought to be re-inferred.

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
- Bulk CSV → Postgres dump pipeline with live progress and failure reporting,
  resumable after a reload, a restart or a power cut.
- Skips images already processed under an identical model setup, so re-running a
  CSV only does the work that is actually new.
- Runtime page showing the last N images dumped, skipped or failed, live.
- Hourly sync of detections to the remote `product-sense` database, run as its
  own process, with an on/off toggle and a `synced_at` watermark.
- Model registry mapping each unique inference setup to one `model_id`.
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
| `POST` | `/api/data-dump/{job_id}/resume` | Continue an interrupted/canceled job from its first unfinished row. |
| `GET` | `/api/sync` · `POST` `/api/sync` | Read sync status / turn the sync on or off. |
| `POST` | `/api/sync/run-now` | Run one sync cycle immediately. |
| `GET` | `/api/models` | Registered inference setups and their `model_id`s. |
| `GET` | `/api/runtime?limit=` | Recent per-image pipeline events, active job, and current config key. |
| `GET` | `/api/confidence?limit=` | Recent classification confidence records (from the Explore Process log). |
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
│   │   ├── maintenance.py      # one-off index build / id + ledger backfill
│   │   ├── sync_service.py     # sync cycle: local -> remote product-sense DB
│   │   ├── config.py           # paths + env configuration
│   │   └── models.py           # pydantic request/response models
│   ├── models/                 # model files are hosted on Hugging Face
│   │   ├── yolo/best.pt
│   │   └── swinv2/<model>/     # HF model dirs (config.json, model.safetensors, …)
│   ├── shop-images/            # mudi shop input images (one folder per shop)
│   ├── uploads/                # runtime generated files (raw/detections/cropped)
│   ├── results/                # runtime reports and logs (runs/, classification_log.jsonl)
│   ├── data/                   # model_config.json (active models + known labels)
│   ├── .env                    # DB_PASSWORD, SYNC_DB_PASSWORD (git-ignored)
│   ├── sync_worker.py          # standalone sync process (systemd / cron)
│   └── run.py
├── requirements.txt            # backend Python dependencies
├── frontend/                   # React 18 + Vite 6 + Tailwind 4
│   ├── src/
│   │   ├── main.jsx            # entry + router
│   │   ├── App.jsx             # layout + routes
│   │   ├── api.js              # backend calls
│   │   ├── index.css           # theme tokens
│   │   ├── components/         # Sidebar, UI primitives
│   │   └── pages/              # ExploreProcess, ModelConfig, DataDump, Runtime
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
