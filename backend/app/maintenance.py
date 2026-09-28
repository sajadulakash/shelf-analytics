"""One-off database maintenance for ShelfAnalytics.

Run with:

    python -m app.maintenance create-indexes
    python -m app.maintenance ledger-status
    python -m app.maintenance backfill-ledger --config-key <key>

These are deliberately *not* part of startup: on an existing
``product_detections`` table they read tens of GB and take minutes, which is
fine to wait for at a prompt and not fine to block the API on.
"""

from __future__ import annotations

import argparse
import sys
import time

from app import db, model_config


def _connect():
    return db.connect(autocommit=True)


def create_indexes() -> int:
    """Build the product_detections(image_id) index.

    CONCURRENTLY, so reads and writes keep working while it builds -- it just
    takes longer. Without this index, any per-image lookup is a full scan of the
    whole table.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*), pg_size_pretty(pg_total_relation_size('product_detections')) "
                        "FROM product_detections")
            rows, size = cur.fetchone()
            print(f"product_detections: {rows:,} rows ({size}). Reads/writes stay available.")
            for name, sql in db.PRODUCT_DETECTIONS_INDEXES:
                cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s", (name,))
                if cur.fetchone():
                    print(f"  {name}: already exists")
                    continue
                print(f"  {name}: building…")
                started = time.time()
                cur.execute(sql)
                print(f"  {name}: created in {time.time() - started:.1f}s")
    finally:
        conn.close()
    return 0


def prepare_sync(pages_per_batch: int, model_id: str | None) -> int:
    """Give every existing row the id (and optionally model_id) the sync needs.

    Walks the table in ctid page ranges rather than one huge UPDATE: a single
    statement over 74M rows would hold one transaction open for the duration and
    balloon the WAL. Each batch commits on its own, so this can be stopped and
    restarted at any point -- it only ever touches rows that are still NULL.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_relation_size('product_detections') / "
                        "current_setting('block_size')::int")
            pages = int(cur.fetchone()[0]) + 1
            cur.execute("SELECT count(*) FROM product_detections WHERE id IS NULL")
            missing = int(cur.fetchone()[0])
            print(f"{missing:,} row(s) without an id, across ~{pages:,} pages.")
            if model_id:
                print(f"model_id will be set to {model_id!r} where it is NULL.")

            done = 0
            started = time.time()
            for start in range(0, pages, pages_per_batch):
                end = start + pages_per_batch
                sets = ["id = gen_random_uuid()::text"]
                where = ["id IS NULL"]
                if model_id:
                    sets.append("model_id = coalesce(model_id, %(model_id)s)")
                    where = ["(id IS NULL OR model_id IS NULL)"]
                cur.execute(
                    f"UPDATE product_detections SET {', '.join(sets)} "
                    f" WHERE ctid >= %(lo)s::tid AND ctid < %(hi)s::tid "
                    f"   AND ({' OR '.join(where)})",
                    {"lo": f"({start},0)", "hi": f"({end},0)", "model_id": model_id},
                )
                done += cur.rowcount
                if done and start % (pages_per_batch * 20) == 0:
                    print(f"  …{done:,} rows updated ({time.time() - started:.0f}s)")
            print(f"Updated {done:,} row(s) in {time.time() - started:.1f}s")

            cur.execute("SELECT count(*) FROM product_detections WHERE id IS NULL")
            print(f"Rows still without an id: {int(cur.fetchone()[0]):,}")
    finally:
        conn.close()

    print("\nNow build the indexes:  python -m app.maintenance create-indexes")
    return 0


def sync_status() -> int:
    """Backlog figures for the remote sync."""
    from app import sync_service

    counts = db.sync_counts()
    print(f"pending (sendable) : {counts['pending']:,}")
    print(f"blocked (no id/model_id): {counts['blocked']:,}")
    print(f"already synced     : {counts['synced']:,}")
    print(f"enabled            : {sync_service.is_enabled()}")
    print(f"password configured: {sync_service.configured()}")
    print(f"destination        : {sync_service.status()['destination']}")
    return 0


def ledger_status() -> int:
    """Show how much of product_detections is covered by the dedup ledger."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM image_inference_runs")
            ledger = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM product_detections")
            detections = cur.fetchone()[0]
            cur.execute("SELECT config_key, count(*) FROM image_inference_runs "
                        "GROUP BY config_key ORDER BY count(*) DESC LIMIT 10")
            per_key = cur.fetchall()
    finally:
        conn.close()

    print(f"ledger rows        : {ledger:,}")
    print(f"detection rows     : {detections:,}")
    print(f"active config key  : {model_config.active_config_key()}")
    if per_key:
        print("per config key:")
        for key, n in per_key:
            print(f"  {key}  {n:,}")
    return 0


def backfill_ledger(config_key: str, batch: int) -> int:
    """Register every image already in product_detections under ``config_key``.

    Only meaningful if those rows really were produced by that setup. Backfilling
    under the *current* key when the old rows came from an older model would make
    the pipeline skip images that ought to be re-inferred -- which is the exact
    failure this ledger exists to prevent. Hence the explicit key argument.
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM product_detections")
            print(f"Scanning {cur.fetchone()[0]:,} detection rows (one pass, grouped by image)…")
            started = time.time()
            cur.execute(
                "INSERT INTO image_inference_runs (image_id, config_key, detections) "
                "SELECT image_id, %s, count(*) FROM product_detections "
                " WHERE image_id IS NOT NULL GROUP BY image_id "
                "ON CONFLICT (image_id, config_key) DO NOTHING",
                (config_key,),
            )
            print(f"Registered {cur.rowcount:,} image(s) under {config_key} "
                  f"in {time.time() - started:.1f}s")
    finally:
        conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.maintenance", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create-indexes", help="build the product_detections indexes")
    sub.add_parser("ledger-status", help="show dedup ledger coverage")
    sub.add_parser("sync-status", help="show the remote sync backlog")

    ps = sub.add_parser("prepare-sync", help="backfill row ids (and model_id) for existing rows")
    ps.add_argument("--pages", type=int, default=20000,
                    help="table pages per batch (default 20000, ~160 MB)")
    ps.add_argument("--model-id", help="also fill model_id where it is NULL")

    bf = sub.add_parser("backfill-ledger", help="register existing detections in the ledger")
    bf.add_argument("--config-key", help="the setup those rows were produced with")
    bf.add_argument("--assume-current", action="store_true",
                    help="use the active config key (only if the data really came from it)")
    bf.add_argument("--batch", type=int, default=100000, help=argparse.SUPPRESS)

    args = parser.parse_args(argv)

    if args.command == "create-indexes":
        return create_indexes()
    if args.command == "ledger-status":
        return ledger_status()
    if args.command == "sync-status":
        return sync_status()
    if args.command == "prepare-sync":
        return prepare_sync(args.pages, args.model_id)

    key = args.config_key
    if args.assume_current:
        key = model_config.active_config_key()
        print(f"Using the active config key: {key}")
        print("Only correct if every existing row was produced by the current models,")
        print("thresholds and label selection. Images registered wrongly will be skipped.")
        if input("Continue? [y/N] ").strip().lower() not in {"y", "yes"}:
            print("Aborted.")
            return 1
    if not key:
        print("Pass --config-key <key> or --assume-current.", file=sys.stderr)
        return 2
    return backfill_ledger(key, args.batch)


if __name__ == "__main__":
    raise SystemExit(main())
