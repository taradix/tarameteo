"""Unit tests for the MELCCFP fetcher."""

import pytest

from tarameteo.melccfp import (
    MelccfpReading,
    _parse_float,
    _parse_page,
    _parse_sensor_coordinates,
)


# Minimal HTML that mirrors the MELCCFP page table structure.
def _row(day, tmax, tavg, tmin, rain, snow_cm):
    """Build a table row matching the real MELCCFP class structure."""
    def bt(v):
        return f'<td class="bordure_t">{v}</td>'
    def spacer(v=""):
        return f'<td class="bordure_TD">{v}</td>'
    return (
        f'<tr><td class="bordure_TGD centrer style2">{day}</td>'
        f'{bt(tmax)}{spacer()}{bt(tavg)}{spacer()}{bt(tmin)}{spacer()}'
        f'<td class="bordure_TD gris"></td>'
        f'{bt(rain)}{spacer()}{bt(snow_cm)}{spacer()}'
        f'<td class="bordure_t">0,0</td>'  # Total (ignored)
        f'</tr>'
    )

FIXTURE_HTML = f"""
<html><body>
<table>
  <tr><th>Jour</th><th>Température</th><th>Précipitation</th></tr>
  <tr>
    <th>Max.(°C)</th><th>Moy.(°C)</th><th>Min.(°C)</th>
    <th>Pluie(mm)</th><th>Neige(cm)</th><th>Total(mm)</th>
  </tr>
  {_row(1, "9,0", "5,5", "2,0", "0,0", "-")}
  {_row(2, "-1,3", "-3,2", "-5,1", "T", "1,5")}
  {_row(3, "-", "-", "-", "-", "-")}
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
    ],
)
def test_parse_float(value, expected):
    assert _parse_float(value) == expected


def test_parse_page_row_count():
    readings = _parse_page(FIXTURE_HTML, year=2025, month=1)
    # Day 3 has all missing values and should be skipped.
    assert len(readings) == 2


def test_parse_page_day1_temperatures():
    readings = _parse_page(FIXTURE_HTML, year=2025, month=1)
    r = readings[0]
    assert r.day == 1
    assert r.temperature_max == 9.0
    assert r.temperature_avg == 5.5
    assert r.temperature_min == 2.0


def test_parse_page_negative_temperatures():
    readings = _parse_page(FIXTURE_HTML, year=2025, month=1)
    r = readings[1]
    assert r.temperature_max == -1.3
    assert r.temperature_avg == -3.2
    assert r.temperature_min == -5.1


def test_parse_page_rain_trace_becomes_zero():
    readings = _parse_page(FIXTURE_HTML, year=2025, month=1)
    assert readings[1].rain == 0.0


def test_parse_page_snow_cm_converted_to_mm():
    readings = _parse_page(FIXTURE_HTML, year=2025, month=1)
    assert readings[1].snow == 15.0  # 1.5 cm -> 15.0 mm


def test_parse_page_no_snow_is_none():
    readings = _parse_page(FIXTURE_HTML, year=2025, month=1)
    assert readings[0].snow is None


def test_parse_page_no_rain_is_zero_not_none():
    readings = _parse_page(FIXTURE_HTML, year=2025, month=1)
    assert readings[0].rain == 0.0


def test_parse_page_skips_future_dates():
    readings = _parse_page(FIXTURE_HTML, year=9999, month=1)
    assert readings == []


def test_parse_page_no_jour_header():
    html = "<html><body><table><tr><td>1</td></tr></table></body></html>"
    readings = _parse_page(html, year=2025, month=1)
    assert readings == []


def test_parse_page_returns_melccfp_readings():
    readings = _parse_page(FIXTURE_HTML, year=2025, month=1)
    assert all(isinstance(r, MelccfpReading) for r in readings)


def test_parse_sensor_coordinates_from_summary_page():
    html = """
    <table>
      <tr>
        <td><strong>Latitude :</strong></td>
        <td>46° 6&#039; 4&#039;&#039;</td>
      </tr>
      <tr>
        <td><strong>Longitude :</strong></td>
        <td>-75° 38&#039; 53&#039;&#039;</td>
      </tr>
      <tr>
        <td><strong>No. station :</strong></td>
        <td>7030M51</td>
      </tr>
    </table>
    """

    latitude, longitude = _parse_sensor_coordinates(html, "7030M51")

    assert latitude == pytest.approx(46.1011111111)
    assert longitude == pytest.approx(-75.6480555556)
