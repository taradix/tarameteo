"""Unit tests for mapping readings to and from time series points."""

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
    AggregateReading(
        sensor="b", timestamp=TS, latitude=45.5, longitude=-73.57,
        temperature_min=-3.0, temperature_max=4.5, snow=12.0,
    ),
    AggregateReading(sensor="c", timestamp=TS, rain=2.0),
])
def test_from_point_reverses_to_point(reading):
    """A stored reading should read back as the same reading."""
    assert_that(from_point(to_point(reading)), equal_to(reading))
