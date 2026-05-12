"""Periodic runner for all registered external weather sources."""

import asyncio
import logging
import os
import signal
from argparse import ArgumentParser
from datetime import UTC, datetime, timedelta

import httpx
from taraqueue import Queue

from tarameteo.logger import (
    LoggerHandlerAction,
    LoggerLevelAction,
    setup_logger,
)
from tarameteo.registry import registry_load
from tarameteo.ts import InfluxWriter

logger = logging.getLogger(__name__)

REGISTRY_GROUP = "tarameteo_source"

# Fetch once per day at 15:05 UTC (= 10:05 EST, 11:05 EDT).
FETCH_UTC_HOUR = 15


def _next_fetch_time() -> datetime:
    now = datetime.now(UTC)
    target = now.replace(hour=FETCH_UTC_HOUR, minute=5, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


async def _run_sync(ts_writer: InfluxWriter, queue: Queue) -> None:
    loop = asyncio.get_running_loop()
    running = True

    def _stop() -> None:
        nonlocal running
        running = False

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _stop)

    registry = registry_load(REGISTRY_GROUP)
    source_modules = list(registry.get(REGISTRY_GROUP, {}).values())
    logger.info(
        "Sources runner started with %d source(s). Press Ctrl+C to stop.",
        len(source_modules),
    )

    async with httpx.AsyncClient(timeout=30) as client:
        for module in source_modules:
            try:
                await module.run_once(client, ts_writer, queue)
            except Exception:
                logger.exception("Error in initial fetch for source %s", module.__name__)

        while running:
            next_run = _next_fetch_time()
            wait_seconds = (next_run - datetime.now(UTC)).total_seconds()
            logger.info("Next fetch at %s (in %.0fs)", next_run.isoformat(), wait_seconds)
            try:
                await asyncio.sleep(wait_seconds)
            except asyncio.CancelledError:
                break
            if not running:
                break
            for module in source_modules:
                try:
                    await module.run_once(client, ts_writer, queue)
                except Exception:
                    logger.exception("Error fetching source %s", module.__name__)


async def _run_backfill(
    ts_writer: InfluxWriter,
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
) -> None:
    registry = registry_load(REGISTRY_GROUP)
    source_modules = list(registry.get(REGISTRY_GROUP, {}).values())

    async with httpx.AsyncClient(timeout=30) as client:
        for module in source_modules:
            try:
                await module.backfill_run(
                    client, ts_writer, from_year, from_month, to_year, to_month
                )
            except Exception:
                logger.exception("Error backfilling source %s", module.__name__)


async def async_main(argv=None) -> None:
    parser = ArgumentParser(prog="tarameteo-sources")
    parser.add_argument("--log-file", action=LoggerHandlerAction)
    parser.add_argument("--log-level", action=LoggerLevelAction)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sync", help="Run the periodic sync loop")

    backfill_parser = subparsers.add_parser(
        "backfill", help="Backfill historical data for all sources"
    )
    backfill_parser.add_argument(
        "--from",
        dest="from_date",
        required=True,
        metavar="YYYY-MM",
        help="First month to backfill (inclusive)",
    )
    backfill_parser.add_argument(
        "--to",
        dest="to_date",
        metavar="YYYY-MM",
        default=None,
        help="Last month to backfill (inclusive, default: current month)",
    )

    args = parser.parse_args(argv)
    setup_logger(args.log_level, args.log_file)

    ts_writer = InfluxWriter.from_env()

    if args.command == "sync":
        queue = Queue.from_url(os.environ["QUEUE_URL"])
        await _run_sync(ts_writer, queue)
    else:
        from_year, from_month = (int(x) for x in args.from_date.split("-"))
        if args.to_date:
            to_year, to_month = (int(x) for x in args.to_date.split("-"))
        else:
            now = datetime.now(UTC)
            to_year, to_month = now.year, now.month
        await _run_backfill(ts_writer, from_year, from_month, to_year, to_month)


def main(argv=None) -> None:
    asyncio.run(async_main(argv))
