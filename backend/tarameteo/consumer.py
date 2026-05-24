"""MQTT consumer service."""

import asyncio
import logging
import signal
from argparse import ArgumentParser
from contextlib import suppress
from datetime import timedelta

from pydantic import ValidationError
from taraqueue import Queue

from tarameteo.alert_checker import DEFAULT_COOLDOWN, check_alerts
from tarameteo.alerts import AlertStore
from tarameteo.db import SessionLocal
from tarameteo.logger import (
    LoggerHandlerAction,
    LoggerLevelAction,
    setup_logger,
)
from tarameteo.mqtt import (
    MQTTConsumer,
    MQTTMessage,
)
from tarameteo.notifier import Notifier
from tarameteo.sensors import WeatherReading
from tarameteo.ts import (
    InfluxWriter,
    TSWriter,
)

logger = logging.getLogger(__name__)


async def weather_handler(
    message: MQTTMessage,
    ts_writer: TSWriter,
    queue: Queue,
    *,
    notifier: Notifier | None = None,
    alert_secret: str = "",
    alert_base_url: str = "",
    alert_cooldown: timedelta = DEFAULT_COOLDOWN,
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
        ts_writer.write_point(
            "weather",
            fields=reading.model_dump(exclude={"sensor", "timestamp", "latitude", "longitude"}, exclude_none=True),
            tags={
                "device_id": device_id,
                "latitude": f"{reading.latitude:.6f}",
                "longitude": f"{reading.longitude:.6f}",
            },
            timestamp=reading.timestamp,
        )
    except ValueError:
        logger.exception("Error storing weather data")
        return

    await queue.publish(f"weather:{device_id}", reading.model_dump_json())

    # Check weather alerts.
    if notifier and alert_secret:
        db = SessionLocal()
        try:
            alert_store = AlertStore(db)
            await check_alerts(
                reading,
                alert_store,
                notifier,
                secret=alert_secret,
                base_url=alert_base_url,
                cooldown=alert_cooldown,
            )
        finally:
            db.close()

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
    notifier: Notifier | None = None,
    alert_secret: str = "",
    alert_base_url: str = "",
    alert_cooldown: timedelta = DEFAULT_COOLDOWN,
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
            notifier=notifier,
            alert_secret=alert_secret,
            alert_base_url=alert_base_url,
            alert_cooldown=alert_cooldown,
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


async def async_main(argv=None) -> None:
    parser = ArgumentParser()
    parser.add_argument(
        "--client-id",
        default="weather-consumer",
        help="Client ID when connecting to MQTT Broker (default: %(default)s)",
    )
    parser.add_argument(
        "--topic-filter",
        default="weather/+/event",
        help="Topic filter to consume from (default: %(default)s)",
    )
    parser.add_argument(
        "--log-file",
        action=LoggerHandlerAction,
    )
    parser.add_argument(
        "--log-level",
        action=LoggerLevelAction,
    )
    args = parser.parse_args(argv)

    setup_logger(args.log_level, args.log_file)

    ts_writer = InfluxWriter.from_env()
    queue = Queue.from_url("memory://")
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, loop.stop)

    logger.info("MQTT consumer started. Press Ctrl+C to stop.")
    await run(ts_writer, queue, client_id=args.client_id, topic=args.topic_filter)


def main(argv=None) -> None:
    asyncio.run(async_main(argv))
