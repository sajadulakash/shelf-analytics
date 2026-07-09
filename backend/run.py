"""Entry point - run with: python run.py

Runs the combined ShelfAnalytics frontend/API server. FastAPI serves the static
frontend from `../frontend` and the API routes from this backend package.
"""

import os

import uvicorn

# Fixed default port for the combined frontend/API server.
DEFAULT_PORT = 8000


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", DEFAULT_PORT))
    print(f"ShelfAnalytics running at http://127.0.0.1:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
