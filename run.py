"""Entry point - run with: python run.py"""

import os
import socket

import uvicorn


def pick_port() -> int:
    configured_port = os.getenv("PORT")
    if configured_port:
        return int(configured_port)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = pick_port()
    print(f"ShelfAnalytics running at http://127.0.0.1:{port}")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
