"""Unit tests for the MELCCFP fetcher."""

import pytest

from tarameteo.melccfp import MelccfpReading, _parse_float, parse_page

# Minimal HTML that mirrors the MELCCFP page table structure.
FIXTURE_HTML = """
<html><body>
<table>
  <tr>
    <th>Jour</th><th>Tmax &#xB0;C</th><th>Tmoy &#xB0;C</th><th>Tmin &#xB0;C</th>
    <th>Pluie mm</th><th>Neige cm</th><th>Total mm</th><th>Neige sol cm</th>
  </tr>
  <tr>
    <td>1</td><td>9,0</td><td>5,5</td><td>2,0</td>
    <td>0,0</td><td>-</td><td>0,0</td><td>-</td>
  </tr>
  <tr>
    <td>2</td><td>-1,3</td><td>-3,2</td><td>-5,1</td>
    <td>T</td><td>1,5</td><td>1,5</td><td>2</td>
  </tr>
  <tr>
    <td>3</td><td>-</td><td>-</td><td>-</td>
    <td>-</td><td>-</td><td>-</td><td>-</td>
  </tr>
</table>
</body></html>
"""


@pytest.mark.parametrize(
    "value,expected",
    [
        ("9,0", 9.0),
        ("-1,3", -1.3),
        ("0,0", 0.0),
        ("-", None),
        (chr(0x2013), None),
        (chr(0x2014), None),
        ("", None),
        ("T", 0.0),
        (" 5,5 ", 5.5),
        ("I", None),
    ],
)
def test_parse_float(value, expected):
    assert _parse_float(value) == expected


def test_parse_page_row_count():
    readings = parse_page(FIXTURE_HTML, year=2025, month=1)
    # Day 3 has all missing values and should be skipped.
    assert len(readings) == 2


def test_parse_page_day1_temperatures():
    readings = parse_page(FIXTURE_HTML, year=2025, month=1)
    r = readings[0]
    assert r.day == 1
    assert r.temperature_max == 9.0
    assert r.temperature_avg == 5.5
    assert r.temperature_min == 2.0


def test_parse_page_negative_temperatures():
    readings = parse_page(FIXTURE_HTML, year=2025, month=1)
    r = readings[1]
    assert r.temperature_max == -1.3
    assert r.temperature_avg == -3.2
    assert r.temperature_min == -5.1


def test_parse_page_rain_trace_becomes_zero():
    readings = parse_page(FIXTURE_HTML, year=2025, month=1)
    assert readings[1].rain == 0.0


def test_parse_page_snow_cm_converted_to_mm():
    readings = parse_page(FIXTURE_HTML, year=2025, month=1)
    assert readings[1].snow == 15.0  # 1.5 cm -> 15.0 mm


def test_parse_page_no_snow_is_none():
    readings = parse_page(FIXTURE_HTML, year=2025, month=1)
    assert readings[0].snow is None


def test_parse_page_no_rain_is_zero_not_none():
    readings = parse_page(FIXTURE_HTML, year=2025, month=1)
    assert readings[0].rain == 0.0


def test_parse_page_skips_future_dates():
    readings = parse_page(FIXTURE_HTML, year=9999, month=1)
    assert readings == []


def test_parse_page_no_jour_header():
    html = "<html><body><table><tr><td>1</td></tr></table></body></html>"
    readings = parse_page(html, year=2025, month=1)
    assert readings == []


def test_parse_page_returns_melccfp_readings():
    readings = parse_page(FIXTURE_HTML, year=2025, month=1)
    assert all(isinstance(r, MelccfpReading) for r in readings)
