"""Unit tests for the METAR fetcher."""


import pytest

from tarameteo.metar import MetarReading, _dewpoint_to_humidity, _parse_observations


def _obs(icao_id, obs_time=1778616000, temp=13, dewp=-3, altim=1019.4, lat=45.307, lon=-75.66, elev=111):
    """Build an AVW METAR observation dict."""
    return {
        "icaoId": icao_id,
        "obsTime": obs_time,
        "temp": temp,
        "dewp": dewp,
        "altim": altim,
        "lat": lat,
        "lon": lon,
        "elev": elev,
    }


FIXTURE_OBS = [
    _obs("CYOW", obs_time=1778616000, temp=13, dewp=-3),
    _obs("CYOW", obs_time=1778612400, temp=12, dewp=-4),  # earlier
    _obs("CWMJ", obs_time=1778616000, temp=10, dewp=5),
    _obs("CXXX", obs_time=1778616000, temp=5, dewp=0),   # unknown station
]


def test_parse_observations_filters_unknown_station():
    readings = _parse_observations(FIXTURE_OBS)
    icaos = {r.icao_id for r in readings}
    assert "CXXX" not in icaos


def test_parse_observations_count():
    readings = _parse_observations(FIXTURE_OBS)
    assert len(readings) == 3


def test_parse_observations_sorted_oldest_first():
    readings = _parse_observations(FIXTURE_OBS)
    cyow = [r for r in readings if r.icao_id == "CYOW"]
    assert cyow[0].timestamp < cyow[1].timestamp


def test_parse_observations_temperature():
    readings = _parse_observations(FIXTURE_OBS)
    cyow = next(r for r in readings if r.icao_id == "CYOW" and r.temperature == 13)
    assert cyow.temperature == 13.0


def test_parse_observations_pressure():
    readings = _parse_observations(FIXTURE_OBS)
    assert readings[0].pressure == pytest.approx(1019.4)


def test_parse_observations_humidity_computed():
    readings = _parse_observations(FIXTURE_OBS)
    cyow = next(r for r in readings if r.icao_id == "CYOW" and r.temperature == 13)
    expected = _dewpoint_to_humidity(13, -3)
    assert cyow.humidity == pytest.approx(expected)


def test_parse_observations_skips_missing_required_field():
    obs = _obs("CYOW")
    obs["dewp"] = None
    assert _parse_observations([obs]) == []


def test_parse_observations_empty():
    assert _parse_observations([]) == []


def test_parse_observations_returns_metar_readings():
    readings = _parse_observations(FIXTURE_OBS)
    assert all(isinstance(r, MetarReading) for r in readings)


@pytest.mark.parametrize("temp,dewp,expected", [
    (13, 13, 100.0),   # saturated
    (13, -3, pytest.approx(32.8, abs=0.5)),
    (0, -10, pytest.approx(46.9, abs=0.5)),
])
def test_dewpoint_to_humidity(temp, dewp, expected):
    assert _dewpoint_to_humidity(temp, dewp) == expected
