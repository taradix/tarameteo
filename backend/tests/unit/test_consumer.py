"""Unit tests for the consumer module."""

import json
from datetime import UTC, datetime

import pytest
from hamcrest import (
    assert_that,
    contains_exactly,
    empty,
    has_entries,
    has_properties,
)
from taraqueue import QueueEmpty

from tarameteo.consumer import weather_handler
from tarameteo.mqtt import MQTTMessage


def make_message(topic="weather/jdd-carre/event", **payload):
    defaults = {
        "timestamp": int(datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC).timestamp()),
        "temperature": 22.5,
        "humidity": 60.0,
        "pressure": 1013.25,
        "latitude": 45.504,
        "longitude": -73.617,
    }
    return MQTTMessage(topic=topic, data={**defaults, **payload}, qos=0, retain=False)


async def test_weather_handler_stores_reading(memory_store, memory_writer, memory_queue):
    await weather_handler(make_message(), ts_writer=memory_writer, queue=memory_queue)

    assert_that(memory_store.points, contains_exactly(
        has_properties(
            measurement="weather",
            tags=has_entries(device_id="jdd-carre"),
        ),
    ))


async def test_weather_handler_stores_all_fields(memory_store, memory_writer, memory_queue):
    await weather_handler(
        make_message(temperature=22.5, humidity=60.0, pressure=1013.25, altitude=150.0, rssi=-70),
        ts_writer=memory_writer,
        queue=memory_queue,
    )

    point = memory_store.points[0]
    assert_that(point.fields["temperature"], 22.5)
    assert_that(point.fields["humidity"], 60.0)
    assert_that(point.fields["pressure"], 1013.25)
    assert_that(point.fields["altitude"], 150.0)
    assert_that(point.fields["rssi"], -70)


async def test_weather_handler_excludes_metadata_from_fields(memory_store, memory_writer, memory_queue):
    await weather_handler(make_message(), ts_writer=memory_writer, queue=memory_queue)

    fields = memory_store.points[0].fields
    assert "timestamp" not in fields
    assert "latitude" not in fields
    assert "longitude" not in fields


async def test_weather_handler_stores_lat_lon_as_tags(memory_store, memory_writer, memory_queue):
    await weather_handler(
        make_message(latitude=45.504, longitude=-73.617),
        ts_writer=memory_writer,
        queue=memory_queue,
    )

    tags = memory_store.points[0].tags
    assert_that(tags, has_entries(latitude="45.504000", longitude="-73.617000"))


async def test_weather_handler_uses_firmware_timestamp(memory_store, memory_writer, memory_queue):
    ts = datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)
    await weather_handler(make_message(timestamp=int(ts.timestamp())), ts_writer=memory_writer, queue=memory_queue)

    stored_ts = memory_store.points[0].timestamp
    assert stored_ts.year == 2026
    assert stored_ts.month == 4


async def test_weather_handler_rejects_invalid_topic(memory_store, memory_writer, memory_queue):
    await weather_handler(make_message(topic="bad/topic"), ts_writer=memory_writer, queue=memory_queue)

    assert_that(memory_store.points, empty())


async def test_weather_handler_rejects_wrong_domain(memory_store, memory_writer, memory_queue):
    await weather_handler(make_message(topic="other/jdd-carre/event"), ts_writer=memory_writer, queue=memory_queue)

    assert_that(memory_store.points, empty())


async def test_weather_handler_falls_back_to_server_time_on_ntp_failure(memory_store, memory_writer, memory_queue):
    # Firmware sends timestamp=0 when NTP sync has not occurred
    before = datetime.now(UTC)
    await weather_handler(make_message(timestamp=0), ts_writer=memory_writer, queue=memory_queue)
    after = datetime.now(UTC)

    assert_that(memory_store.points, contains_exactly(
        has_properties(measurement="weather"),
    ))
    stored_ts = memory_store.points[0].timestamp
    assert before <= stored_ts <= after


async def test_weather_handler_publishes_to_sensor_channel(memory_writer, memory_queue, unique):
    name = unique("text")
    async with memory_queue.connect(f"weather:{name}") as q:
        await weather_handler(
            make_message(topic=f"weather/{name}/event", temperature=22.5, humidity=60.0, pressure=1013.25),
            ts_writer=memory_writer,
            queue=q,
        )
        message = await q.receive()

    data = json.loads(message)
    assert_that(data, has_entries(sensor=name, temperature=22.5, humidity=60.0, pressure=1013.25))


async def test_weather_handler_publishes_to_correct_channel(memory_writer, memory_queue, unique):
    name = unique("text")
    async with memory_queue.connect(f"weather:{name}") as q:
        await weather_handler(
            make_message(topic=f"weather/{name}/event"),
            ts_writer=memory_writer,
            queue=q,
        )
        message = await q.receive()

    assert json.loads(message)["temperature"] == 22.5


async def test_weather_handler_does_not_publish_on_invalid_topic(memory_writer, memory_queue):
    # Subscribe to the channel that would be written if publishing occurred.
    async with memory_queue.connect("weather:jdd-carre") as q:
        await weather_handler(make_message(topic="bad/topic"), ts_writer=memory_writer, queue=q)
        with pytest.raises(QueueEmpty):
            await q.receive()


async def test_weather_handler_raises_unexpected_write_errors(memory_queue):
    class BrokenWriter:
        def write_point(self, *args, **kwargs):
            raise RuntimeError("write failure")

    with pytest.raises(RuntimeError, match="write failure"):
        await weather_handler(make_message(), ts_writer=BrokenWriter(), queue=memory_queue)


async def test_weather_handler_raises_publish_errors(memory_writer):
    class BrokenQueue:
        async def publish(self, channel, message):
            raise RuntimeError("publish failure")

    with pytest.raises(RuntimeError, match="publish failure"):
        await weather_handler(make_message(), ts_writer=memory_writer, queue=BrokenQueue())
