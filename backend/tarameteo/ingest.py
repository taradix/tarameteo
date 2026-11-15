"""Single path for new readings from every source: store, publish, check alerts."""

import asyncio
import logging
from collections.abc import Sequence

from taraqueue import Queue

from tarameteo.alert_checker import AlertService
from tarameteo.readings import Reading, to_point
from tarameteo.ts import TSWriter

logger = logging.getLogger(__name__)


def write_readings(ts_writer: TSWriter, readings: Sequence[Reading]) -> None:
    """Store readings, skipping aggregates without any value."""
    points = [to_point(r) for r in readings]
    ts_writer.write_points([p for p in points if p.fields])


async def ingest(
    readings: Sequence[Reading],
    ts_writer: TSWriter,
    queue: Queue,
    *,
    alerts: AlertService | None = None,
) -> None:
    """Store readings, then publish and check alerts on each sensor's latest one (readings oldest first)."""
    # The write blocks (HTTP, retries with sleep), so keep it off the loop that also serves the API.
    await asyncio.to_thread(write_readings, ts_writer, readings)
    latest = {r.sensor: r for r in readings}
    for reading in latest.values():
        await queue.publish(f"weather:{reading.sensor}", reading.model_dump_json())
        if alerts:
            try:
                await alerts.check_reading(reading)
            except Exception:
                # Keep ingesting the other sensors and the next readings.
                logger.exception("Failed to check alerts for %s", reading.sensor)
