"""Periodic runner for all registered external weather sources."""

import asyncio
import logging
import signal
from argparse import ArgumentParser
from contextlib import suppress
from datetime import UTC, datetime, timedelta

import httpx
from taraqueue import Queue

from tarameteo.logger import (
    LoggerHandlerAction,
    LoggerLevelAction,
    setup_logger,
)
from tarameteo.registry import registry_load
from tarameteo.source import Source
from tarameteo.ts import InfluxWriter

logger = logging.getLogger(__name__)

REGISTRY_GROUP = "tarameteo_source"


def _select_sources(registry: dict, names: list[str]) -> list:
    all_sources = registry.get(REGISTRY_GROUP, {})
    if not names:
        return list(all_sources.values())
    unknown = [n for n in names if n not in all_sources]
    if unknown:
        raise SystemExit(f"Unknown source(s): {', '.join(unknown)}. Available: {', '.join(all_sources)}")
    return [all_sources[n] for n in names]

SYNC_INTERVAL = timedelta(hours=1)


def _next_fetch_time() -> datetime:
    return datetime.now(UTC) + SYNC_INTERVAL


async def _run_source_once(source: Source, client: httpx.AsyncClient, ts_writer: InfluxWriter, queue: Queue) -> None:
    try:
        await source.run_once(client, ts_writer, queue)
    except source.RECOVERABLE_ERRORS:
        logger.exception("Recoverable error while fetching source %s", source.name)


async def _run_source_backfill(
    source: Source,
    client: httpx.AsyncClient,
    ts_writer: InfluxWriter,
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
) -> None:
    try:
        await source.backfill_run(
            client, ts_writer, from_year, from_month, to_year, to_month,
        )
    except source.RECOVERABLE_ERRORS:
        logger.exception("Recoverable error backfilling source %s", source.name)


async def run_sync(ts_writer: InfluxWriter, queue: Queue, names: list[str] | None = None) -> None:
    """Run the periodic sources sync loop as a long-lived coroutine.

    Intended to be launched as an :mod:`asyncio` background task from the
    FastAPI lifespan.  Exits cleanly on :exc:`asyncio.CancelledError`.
    """
    registry = registry_load(REGISTRY_GROUP)
    sources = _select_sources(registry, names or [])
    logger.info(
        "Sources runner started with %d source(s).",
        len(sources),
    )

    async with httpx.AsyncClient(timeout=30) as client:
        for source in sources:
            await _run_source_once(source, client, ts_writer, queue)

        while True:
            next_run = _next_fetch_time()
            wait_seconds = (next_run - datetime.now(UTC)).total_seconds()
            logger.info("Next fetch at %s (in %.0fs)", next_run.isoformat(), wait_seconds)
            try:
                await asyncio.sleep(wait_seconds)
            except asyncio.CancelledError:
                logger.info("Sources runner stopping.")
                return
            for source in sources:
                await _run_source_once(source, client, ts_writer, queue)


async def _run_backfill(
    ts_writer: InfluxWriter,
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
    names: list[str],
) -> None:
    registry = registry_load(REGISTRY_GROUP)
    sources = _select_sources(registry, names)

    async with httpx.AsyncClient(timeout=30) as client:
        for source in sources:
            await _run_source_backfill(
                source, client, ts_writer, from_year, from_month, to_year, to_month,
            )


async def async_main(argv=None) -> None:
    parser = ArgumentParser(prog="tarameteo-sources")
    parser.add_argument("--log-file", action=LoggerHandlerAction)
    parser.add_argument("--log-level", action=LoggerLevelAction)
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="Run the periodic sync loop")
    sync_parser.add_argument(
        "sources",
        nargs="*",
        metavar="SOURCE",
        help="Sources to sync (default: all)",
    )

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
    backfill_parser.add_argument(
        "sources",
        nargs="*",
        metavar="SOURCE",
        help="Sources to backfill (default: all)",
    )

    args = parser.parse_args(argv)
    setup_logger(args.log_level, args.log_file)

    ts_writer = InfluxWriter.from_env()

    if args.command == "sync":
        loop = asyncio.get_running_loop()
        task = loop.create_task(run_sync(ts_writer, Queue.from_url("memory://"), args.sources))

        def _stop() -> None:
            task.cancel()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _stop)

        with suppress(asyncio.CancelledError):
            await task
    else:
        from_year, from_month = (int(x) for x in args.from_date.split("-"))
        if args.to_date:
            to_year, to_month = (int(x) for x in args.to_date.split("-"))
        else:
            now = datetime.now(UTC)
            to_year, to_month = now.year, now.month
        await _run_backfill(ts_writer, from_year, from_month, to_year, to_month, args.sources)


def main(argv=None) -> None:
    asyncio.run(async_main(argv))
