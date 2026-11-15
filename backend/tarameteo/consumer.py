"""MQTT consumer, run by the API as a background task.

There is no separate consumer process: a second one would write every
reading twice and need its own MQTT client id.
"""

import asyncio
import logging
from contextlib import suppress

from pydantic import ValidationError
from taraqueue import Queue

from tarameteo.alert_checker import AlertService
from tarameteo.ingest import ingest
from tarameteo.mqtt import (
    MQTTConsumer,
    MQTTMessage,
)
from tarameteo.readings import WeatherReading
from tarameteo.ts import TSWriter

logger = logging.getLogger(__name__)


async def weather_handler(
    message: MQTTMessage,
    ts_writer: TSWriter,
    queue: Queue,
    *,
    alerts: AlertService | None = None,
):
    try:
        domain, device_id, category = message.topic.split("/")
    except ValueError:
        logger.warning(f"Invalid topic format: {message.topic}")
        return

    if domain != "weather" or category != "event":
        logger.warning(f"Invalid topic: {message.topic}")
        return

    try:
        reading = WeatherReading(sensor=device_id, **message.data)
    except (ValidationError, TypeError):
        logger.exception("Invalid weather data format")
        return

    try:
        await ingest([reading], ts_writer, queue, alerts=alerts)
    except ValueError:
        logger.exception("Error storing weather data")
        return

    logger.info(
        f"Stored weather data for sensor {device_id}: "
        f"T={reading.temperature}°C"
        f", H={reading.humidity}%"
        f", P={reading.pressure}hPa"
        + (f", RSSI={reading.rssi}dBm" if reading.rssi else "")
    )


async def run(
    ts_writer: TSWriter,
    queue: Queue,
    client_id: str = "weather-consumer",
    topic: str = "weather/+/event",
    *,
    alerts: AlertService | None = None,
) -> None:
    """Run the MQTT consumer as a long-lived coroutine.

    Intended to be launched as an :mod:`asyncio` background task from the
    FastAPI lifespan.  Exits cleanly on :exc:`asyncio.CancelledError`.
    """
    loop = asyncio.get_running_loop()

    async def _async_handler(message: MQTTMessage) -> None:
        await weather_handler(
            message,
            ts_writer=ts_writer,
            queue=queue,
            alerts=alerts,
        )

    def _log_handler_failure(future) -> None:
        with suppress(asyncio.CancelledError):
            exc = future.exception()
        if exc is not None:
            logger.error("Unhandled error in weather message handler", exc_info=exc)

    def _sync_handler(message: MQTTMessage) -> None:
        future = asyncio.run_coroutine_threadsafe(_async_handler(message), loop)
        future.add_done_callback(_log_handler_failure)

    consumer = MQTTConsumer.from_env(
        client_id=client_id,
        topic=topic,
        on_message=_sync_handler,
    )
    consumer.connect()
    logger.info("MQTT consumer started.")
    try:
        while consumer.running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("MQTT consumer stopping.")
    finally:
        consumer.disconnect()
