"""Unit tests for the consumer module."""

from datetime import UTC, datetime

from hamcrest import (
    assert_that,
    contains_exactly,
    empty,
    has_properties,
)

from tarameteo.consumer import weather_handler
from tarameteo.mqtt import MQTTMessage


def make_message(topic="weather/jdd-carre/event", **payload):
    defaults = {
        "timestamp": int(datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC).timestamp()),
        "temperature": 22.5,
        "humidity": 60.0,
        "pressure": 1013.25,
    }
    return MQTTMessage(topic=topic, data={**defaults, **payload}, qos=0, retain=False)


def test_weather_handler_stores_reading(memory_store, memory_writer):
    weather_handler(make_message(), ts_writer=memory_writer)

    assert_that(memory_store.points, contains_exactly(
        has_properties(
            measurement="weather",
            tags={"device_id": "jdd-carre"},
        ),
    ))


def test_weather_handler_stores_all_fields(memory_store, memory_writer):
    weather_handler(
        make_message(temperature=22.5, humidity=60.0, pressure=1013.25, altitude=150.0, rssi=-70),
        ts_writer=memory_writer,
    )

    point = memory_store.points[0]
    assert_that(point.fields["temperature"], 22.5)
    assert_that(point.fields["humidity"], 60.0)
    assert_that(point.fields["pressure"], 1013.25)
    assert_that(point.fields["altitude"], 150.0)
    assert_that(point.fields["rssi"], -70)


def test_weather_handler_excludes_timestamp_from_fields(memory_store, memory_writer):
    weather_handler(make_message(), ts_writer=memory_writer)

    assert "timestamp" not in memory_store.points[0].fields


def test_weather_handler_uses_firmware_timestamp(memory_store, memory_writer):
    ts = datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)
    weather_handler(make_message(timestamp=int(ts.timestamp())), ts_writer=memory_writer)

    stored_ts = memory_store.points[0].timestamp
    assert stored_ts.year == 2026
    assert stored_ts.month == 4


def test_weather_handler_rejects_invalid_topic(memory_store, memory_writer):
    weather_handler(make_message(topic="bad/topic"), ts_writer=memory_writer)

    assert_that(memory_store.points, empty())


def test_weather_handler_rejects_wrong_domain(memory_store, memory_writer):
    weather_handler(make_message(topic="other/jdd-carre/event"), ts_writer=memory_writer)

    assert_that(memory_store.points, empty())


def test_weather_handler_falls_back_to_server_time_on_ntp_failure(memory_store, memory_writer):
    # millis() fallback: firmware boot time in ms treated as seconds → year 1970
    before = datetime.now(UTC)
    weather_handler(make_message(timestamp=30000), ts_writer=memory_writer)
    after = datetime.now(UTC)

    assert_that(memory_store.points, contains_exactly(
        has_properties(measurement="weather"),
    ))
    stored_ts = memory_store.points[0].timestamp
    assert before <= stored_ts <= after
