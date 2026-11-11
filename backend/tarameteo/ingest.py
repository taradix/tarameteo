"""Single path for new readings from every source: store, publish, check alerts."""

import asyncio
import logging
from collections.abc import Sequence

from taraqueue import Queue

from tarameteo.alert_checker import check_reading
from tarameteo.notifier import Notifier
from tarameteo.sensors import (
    AGGREGATE_MEASUREMENT,
    MEASUREMENT,
    SENSOR_TAG,
    AggregateReading,
    WeatherReading,
)
from tarameteo.ts import TSPoint, TSWriter

logger = logging.getLogger(__name__)

Reading = WeatherReading | AggregateReading


def to_point(reading: Reading) -> TSPoint:
    """Map a reading to its Influx point: location as tags, measurements as fields."""
    tags = {SENSOR_TAG: reading.sensor}
    if reading.latitude is not None and reading.longitude is not None:
        tags |= {"latitude": f"{reading.latitude:.6f}", "longitude": f"{reading.longitude:.6f}"}
    return TSPoint(
        measurement=MEASUREMENT if isinstance(reading, WeatherReading) else AGGREGATE_MEASUREMENT,
        fields=reading.model_dump(exclude={"sensor", "timestamp", "latitude", "longitude"}, exclude_none=True),
        tags=tags,
        timestamp=reading.timestamp,
    )


def write_readings(ts_writer: TSWriter, readings: Sequence[Reading]) -> None:
    """Store readings, skipping aggregates without any value."""
    points = [to_point(r) for r in readings]
    ts_writer.write_points([p for p in points if p.fields])


async def ingest(
    readings: Sequence[Reading],
    ts_writer: TSWriter,
    queue: Queue,
    *,
    notifier: Notifier | None = None,
    alert_secret: str = "",
    alert_base_url: str = "",
) -> None:
    """Store readings, then publish and check alerts on each sensor's latest one (readings oldest first)."""
    # The write blocks (HTTP, retries with sleep), so keep it off the loop that also serves the API.
    await asyncio.to_thread(write_readings, ts_writer, readings)
    latest = {r.sensor: r for r in readings}
    for reading in latest.values():
        await queue.publish(f"weather:{reading.sensor}", reading.model_dump_json())
        if notifier and alert_secret:
            try:
                await check_reading(reading, notifier, secret=alert_secret, base_url=alert_base_url)
            except Exception:
                # Keep ingesting the other sensors and the next readings.
                logger.exception("Failed to check alerts for %s", reading.sensor)
