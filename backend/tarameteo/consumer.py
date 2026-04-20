"""MQTT consumer service."""

import asyncio
import logging
import signal
from argparse import ArgumentParser
from functools import partial

from pydantic import ValidationError

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


def weather_handler(ts_writer: TSWriter, message: MQTTMessage):
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
    except ValidationError:
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
    handler = partial(weather_handler, ts_writer=ts_writer)
    consumer = MQTTConsumer.from_env(
        client_id=args.client_id,
        topic=args.topic_filter,
        on_message=handler,
    )
    consumer.connect()

    # Handle signals
    loop = asyncio.get_running_loop()
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
