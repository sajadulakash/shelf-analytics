"""Entry point - run with: python run.py

Runs the backend API only. The frontend is a separate static app under
`../frontend`; it reaches this server via the API base configured in
`frontend/assets/js/config.js` (defaults to http://127.0.0.1:8000).
"""

import os

import uvicorn

# Fixed default port so the standalone frontend has a stable API target.
DEFAULT_PORT = 8000


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", DEFAULT_PORT))
    print(f"ShelfAnalytics API running at http://127.0.0.1:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
