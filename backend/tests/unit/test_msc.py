"""Unit tests for the MSC hourly fetcher."""

import pytest

from tarameteo.msc import MscReading, parse_features


def _feature(day, hour, utc_date, temp=None, humidity=None, pressure_kpa=None, lat=46.27, lon=-75.99, rain=None):
    """Build a GeoMet climate-hourly feature dict."""
    return {
        "properties": {
            "LOCAL_DAY": day,
            "LOCAL_HOUR": hour,
            "UTC_DATE": utc_date,
            "TEMP": temp,
            "RELATIVE_HUMIDITY": humidity,
            "STATION_PRESSURE": pressure_kpa,
            "LATITUDE_DECIMAL_DEGREES": lat,
            "LONGITUDE_DECIMAL_DEGREES": lon,
            "PRECIP_AMOUNT": rain,
        }
    }


FIXTURE_FEATURES = [
    _feature(1, 9, "2025-01-01T14:00:00", temp=-2.3, humidity=75, pressure_kpa=98.94, rain=0.0),
    _feature(1, 10, "2025-01-01T15:00:00", temp=-1.8, humidity=72, pressure_kpa=99.10, rain=None),
    _feature(2, 0, "2025-01-02T05:00:00", temp=None, humidity=80, pressure_kpa=99.0, rain=None),  # missing temp
]


def test_parse_features_count():
    readings = parse_features(FIXTURE_FEATURES, year=2025, month=1)
    # Third feature is missing temp and should be skipped.
    assert len(readings) == 2


def test_parse_features_temperature():
    readings = parse_features(FIXTURE_FEATURES, year=2025, month=1)
    assert readings[0].temperature == -2.3
    assert readings[1].temperature == -1.8


def test_parse_features_pressure_converted_to_hpa():
    readings = parse_features(FIXTURE_FEATURES, year=2025, month=1)
    assert readings[0].pressure == pytest.approx(989.4)


def test_parse_features_rain_present():
    readings = parse_features(FIXTURE_FEATURES, year=2025, month=1)
    assert readings[0].rain == 0.0


def test_parse_features_rain_none():
    readings = parse_features(FIXTURE_FEATURES, year=2025, month=1)
    assert readings[1].rain is None


def test_parse_features_utc_timestamp():
    readings = parse_features(FIXTURE_FEATURES, year=2025, month=1)
    assert readings[0].utc_timestamp.hour == 14
    assert readings[0].utc_timestamp.tzinfo is not None


def test_parse_features_skips_future():
    features = [_feature(1, 0, "9999-01-01T00:00:00", temp=5.0, humidity=80, pressure_kpa=99.0)]
    assert parse_features(features, year=9999, month=1) == []


def test_parse_features_empty():
    assert parse_features([], year=2025, month=1) == []


def test_parse_features_returns_msc_readings():
    readings = parse_features(FIXTURE_FEATURES, year=2025, month=1)
    assert all(isinstance(r, MscReading) for r in readings)


@pytest.mark.parametrize("day", [0, 32, "x", None])
def test_parse_features_invalid_day_skipped(day):
    features = [_feature(day, 0, "2025-01-01T00:00:00", temp=5.0, humidity=80, pressure_kpa=99.0)]
    assert parse_features(features, year=2025, month=1) == []
