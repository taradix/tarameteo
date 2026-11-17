"""Unit tests for mapping readings to and from time series points."""

import json
from datetime import (
    UTC,
    datetime,
)

import pytest
from hamcrest import (
    assert_that,
    equal_to,
)

from tarameteo.readings import (
    AggregateReading,
    WeatherReading,
    from_point,
    to_point,
)

TS = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize("reading", [
    WeatherReading(
        sensor="a", timestamp=TS, temperature=20.5, humidity=50.0, pressure=1013.25,
        latitude=46.81, longitude=-71.21, rain=1.5, rssi=-60, retry_count=2,
    ),
    WeatherReading(
        sensor="tm-3f9a1c", label="Serre à tomates", timestamp=TS, temperature=1.0, humidity=2.0, pressure=3.0,
        latitude=46.81, longitude=-71.21,
    ),
    AggregateReading(
        sensor="b", timestamp=TS, latitude=45.5, longitude=-73.57,
        temperature_min=-3.0, temperature_max=4.5, snow=12.0,
    ),
    AggregateReading(sensor="c", timestamp=TS, rain=2.0),
])
def test_from_point_reverses_to_point(reading):
    """A stored reading should read back as the same reading."""
    assert_that(from_point(to_point(reading)), equal_to(reading))


# Copies of what MqttClient::buildPayload in the firmware publishes. Flashed
# sensors can't be updated, so this payload must keep parsing: see the
# additive-only rule in CONTRIBUTING.rst.
@pytest.mark.parametrize("payload, expected", [
    (
        '{"timestamp":1767225600,"temperature":20.5,"humidity":50,"pressure":1013.25,'
        '"latitude":46.81,"longitude":-71.21}',
        {"temperature": 20.5, "humidity": 50.0, "pressure": 1013.25, "altitude": None, "rssi": None},
    ),
    (
        '{"timestamp":1767225600,"temperature":20.5,"humidity":50,"pressure":1013.25,'
        '"latitude":46.81,"longitude":-71.21,"altitude":150.5,"rssi":-60,"retry_count":2}',
        {"altitude": 150.5, "rssi": -60, "retry_count": 2},
    ),
    (
        '{"timestamp":1767225600,"temperature":20.5,"humidity":50,"pressure":1013.25,'
        '"latitude":46.81,"longitude":-71.21,"label":"Abri été"}',
        {"label": "Abri été"},
    ),
])
def test_weather_reading_parses_firmware_payload(payload, expected):
    """The JSON a sensor publishes should parse into a reading."""
    reading = WeatherReading(sensor="a", **json.loads(payload))

    assert_that(reading.timestamp, equal_to(TS))
    assert_that(reading.model_dump(include=set(expected)), equal_to(expected))


@pytest.mark.parametrize("label", ["", "a" * 33, "Gazebo\nBcc: x@example.com"])
def test_rejects_bad_labels(label):
    """A label is a tag and goes into email subjects, so it can't be empty, long or hold control characters."""
    with pytest.raises(ValueError):
        WeatherReading(
            sensor="a", label=label, timestamp=TS, temperature=1.0, humidity=2.0, pressure=3.0, latitude=0.0, longitude=0.0,
        )
