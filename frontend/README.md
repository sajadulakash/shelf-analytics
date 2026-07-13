# ShelfAnalytics – Web (React)

Modern React frontend (Vite + Tailwind CSS) that replaces the static
`../frontend` app. Sidebar layout, and the Explore Process page talks to the
FastAPI backend.

## Develop

```bash
npm install          # once — downloads React/Vite/Tailwind into node_modules
npm run dev          # http://localhost:5173
```

Start the backend too (`cd ../backend && python run.py`, port 8000). In dev,
Vite proxies `/api`, `/detect-shelf`, `/classify-detected-crops`, `/uploads`,
etc. to the backend, so the app calls them same-origin — no CORS setup needed.

If the backend runs elsewhere, set `VITE_BACKEND` (dev proxy target):

```bash
VITE_BACKEND=http://192.168.68.64:8000 npm run dev
```

## Build

```bash
npm run build        # outputs static files to dist/
npm run preview      # preview the production build
```

For production you can serve `dist/` from any static host, or point the
FastAPI backend at it. When the built app is served from a different origin
than the API, set `VITE_API_BASE` at build time:

```bash
VITE_API_BASE=http://192.168.68.64:8000 npm run build
```

## Pages

- **Explore Process** (`/`) — upload a shelf image → detect (YOLO+SAHI) →
  classify (SwinV2) → report + PDF. Calls the real backend.
- **Model Configuration** (`/models`) — model + SAHI mode selectors (simulated).
- **Database Data Dump** (`/data-dump`) — CSV bulk flow with a simulated
  process timeline.
- **Confidence** (`/confidence`) — live classification confidence log.

## Structure

```
src/
├── main.jsx            # entry + router
├── App.jsx             # layout + routes
├── api.js              # backend calls
├── components/         # Sidebar, UI primitives
└── pages/              # ExploreProcess, ModelConfig, DataDump, Confidence
```
