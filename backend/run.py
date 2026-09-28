"""Entry point - run with: python run.py

Runs the ShelfAnalytics API server. The React frontend is served separately by
Vite (`cd ../frontend && npm run dev`).

Hot-reload is OFF by default: a reload restarts the process and cuts off any
running Database Data Dump job. Set RELOAD=1 while developing.
"""

import os

import uvicorn

# Fixed default port for the combined frontend/API server.
DEFAULT_PORT = 8000


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", DEFAULT_PORT))
    reload = os.getenv("RELOAD", "0").strip().lower() in {"1", "true", "yes", "on"}
    print(f"ShelfAnalytics API running at http://127.0.0.1:{port}")
    if reload:
        print("Hot-reload is ON - a code change will interrupt running data-dump jobs.")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
