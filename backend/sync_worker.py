"""Standalone sync worker - run with: python sync_worker.py

Pushes local detections to the remote product-sense database. This is a separate
process from the API on purpose: it talks straight to the database and does not
care whether an inference job is running, whether the API is up, or whether
anyone has a browser open. All it looks at is ``product_detections`` rows whose
``synced_at`` is NULL.

    python sync_worker.py            # run forever, a cycle every SYNC_INTERVAL_SECONDS
    python sync_worker.py --once     # run one cycle and exit (for cron)
    python sync_worker.py --force    # ignore the on/off toggle for this run

The on/off toggle set on the Database Data Dump page lives in the database
(``app_settings.sync_enabled``), so this worker sees it without any shared file.

Run it under systemd:

    [Unit]
    Description=ShelfAnalytics sync worker
    After=network-online.target postgresql.service

    [Service]
    WorkingDirectory=/home/sajadulakash/Desktop/ShelfAnalytics/backend
    ExecStart=/home/sajadulakash/miniconda3/envs/shelf-a/bin/python sync_worker.py
    Restart=always
    RestartSec=10

    [Install]
    WantedBy=multi-user.target

...or from cron, once an hour:

    0 * * * * cd /home/sajadulakash/Desktop/ShelfAnalytics/backend && \
      /home/sajadulakash/miniconda3/envs/shelf-a/bin/python sync_worker.py --once
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app import config, db, sync_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("sync_worker")


async def _once(force: bool) -> int:
    if not sync_service.configured():
        logger.error("SYNC_DB_PASSWORD is not set in backend/.env; nothing to do.")
        return 2
    if not force and not sync_service.is_enabled():
        logger.info("Sync is switched off (enable it on the Database Data Dump page).")
        return 0

    counts = db.sync_counts()
    logger.info(
        "Pending %s | blocked %s | already synced %s",
        f"{counts['pending']:,}", f"{counts['blocked']:,}", f"{counts['synced']:,}",
    )
    if counts["blocked"]:
        logger.warning(
            "%s row(s) have no id or model_id and will be left alone "
            "(python -m app.maintenance prepare-sync).", f"{counts['blocked']:,}",
        )
    result = await sync_service.run_now()
    logger.info("Done: %s", result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sync_worker", description=__doc__)
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit")
    parser.add_argument("--force", action="store_true", help="run even if the toggle is off")
    args = parser.parse_args(argv)

    try:
        db.ensure_schema()
    except Exception as e:  # noqa: BLE001
        logger.error("Local database unreachable: %s", e)
        return 2

    if args.once:
        return asyncio.run(_once(args.force))

    logger.info(
        "Sync worker running. Destination %s, every %ds, %d rows per batch.",
        f"{config.SYNC_DB_NAME}.{config.SYNC_TABLE} @ {config.SYNC_DB_HOST}",
        config.SYNC_INTERVAL_SECONDS, config.SYNC_BATCH_SIZE,
    )
    try:
        asyncio.run(sync_service.loop())
    except KeyboardInterrupt:
        logger.info("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
