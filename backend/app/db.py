"""Postgres access for the Database Data Dump pipeline.

Thin, synchronous psycopg2 layer. The data-dump consumer runs one image at a
time, so a single connection per job (used serially) is enough — callers invoke
these helpers from a worker thread via ``asyncio.to_thread``.
"""

from __future__ import annotations

from typing import Iterable

import psycopg2
from psycopg2.extras import execute_values

from app import config

# One row per detected + classified product.
_INSERT_SQL = (
    "INSERT INTO product_detections "
    "(image_id, class_name, x_center, y_center, bbox_width, bbox_height) VALUES %s"
)

DetectionRow = tuple[str, str, float, float, float, float]


def connect():
    """Open a new Postgres connection using the configured credentials."""
    return psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


def ping() -> None:
    """Raise if the database is unreachable (fail fast before a run starts)."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    finally:
        conn.close()


def insert_detections(conn, rows: Iterable[DetectionRow]) -> int:
    """Bulk-insert detection rows; returns the number written."""
    rows = list(rows)
    if not rows:
        return 0
    with conn.cursor() as cur:
        execute_values(cur, _INSERT_SQL, rows)
    conn.commit()
    return len(rows)
