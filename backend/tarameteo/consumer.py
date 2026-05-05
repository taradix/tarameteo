"""MQTT consumer service."""

import asyncio
import logging
import os
import signal
from argparse import ArgumentParser

from taraqueue import Queue

from tarameteo.logger import (
    LoggerHandlerAction,
    LoggerLevelAction,
    setup_logger,
)
from tarameteo.mqtt import (
    MQTTConsumer,
    MQTTMessage,
)
from tarameteo.ts import (
    InfluxWriter,
    TSWriter,
)
from tarameteo.weather import WeatherDataRequest

logger = logging.getLogger(__name__)


async def weather_handler(message: MQTTMessage, ts_writer: TSWriter, queue: Queue):
    try:
        domain, device_id, category = message.topic.split("/")
    except ValueError:
        logger.warning(f"Invalid topic format: {message.topic}")
        return

    if domain != "weather" or category != "event":
        logger.warning(f"Invalid topic: {message.topic}")
        return

    try:
        weather_data = WeatherDataRequest(**message.data)
    except Exception:
        logger.exception("Invalid weather data format")
        return

    fields = weather_data.model_dump(exclude={"timestamp"}, exclude_none=True)
    try:
        ts_writer.write_point(
            "weather",
            fields=fields,
            tags={"device_id": device_id},
            timestamp=weather_data.timestamp,
        )
    except Exception:
        logger.exception("Error storing weather data")
        return

    try:
        await queue.publish(f"weather:{device_id}", weather_data.model_dump_json())
    except Exception:
        logger.exception("Error publishing weather data to queue")

    logger.info(
        f"Stored weather data for sensor {device_id}: "
        f"T={weather_data.temperature}°C"
        f", H={weather_data.humidity}%"
        f", P={weather_data.pressure}hPa"
        + (f", RSSI={weather_data.rssi}dBm" if weather_data.rssi else "")
    )


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
    queue = Queue.from_url(os.environ["QUEUE_URL"])
    loop = asyncio.get_running_loop()

    async def _async_handler(message: MQTTMessage) -> None:
        await weather_handler(message, ts_writer=ts_writer, queue=queue)

    def _sync_handler(message: MQTTMessage) -> None:
        asyncio.run_coroutine_threadsafe(_async_handler(message), loop)

    consumer = MQTTConsumer.from_env(
        client_id=args.client_id,
        topic=args.topic_filter,
        on_message=_sync_handler,
    )
    consumer.connect()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, consumer.disconnect)

    logger.info("MQTT consumer started. Press Ctrl+C to stop.")

    try:
        while consumer.running:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        consumer.disconnect()


def main(argv=None) -> None:
    asyncio.run(async_main(argv))
