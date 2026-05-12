"""MELCCFP (Quebec Environment ministry) weather station fetcher."""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from bs4 import BeautifulSoup
from taraqueue import Queue

from tarameteo.sensors import (
    AGGREGATE_MEASUREMENT,
    SENSOR_TAG,
    AggregateReading,
)
from tarameteo.ts import TSWriter

logger = logging.getLogger(__name__)

BASE_URL = "https://www.environnement.gouv.qc.ca/climat/donnees/sommaire.asp"

# French locale dash variants used as missing-value markers on the page.
_EN_DASH = chr(0x2013)  # en dash
_EM_DASH = chr(0x2014)  # em dash


@dataclass(frozen=True)
class MelccfpSensor:
    device_id: str
    key: str


# Sensors to fetch from the MELCCFP climate data portal.
# Each entry produces one aggregate sensor in the time series store.
SENSORS: list[MelccfpSensor] = [
    MelccfpSensor(device_id="melccfp-barrage-rapides-cedres", key="7030M51"),
]


@dataclass
class MelccfpReading:
    year: int
    month: int
    day: int
    temperature_max: float | None
    temperature_avg: float | None
    temperature_min: float | None
    rain: float | None
    snow: float | None


def _parse_float(value: str) -> float | None:
    """Parse a French-locale number from a MELCCFP page.

    Handles missing values ("-", en-dash, em-dash, empty string),
    trace amounts ("T" -> 0.0), and comma decimal separators.
    """
    stripped = value.strip()
    if not stripped or stripped in ("-", _EN_DASH, _EM_DASH):
        return None
    if stripped == "T":
        return 0.0
    return float(stripped.replace(",", "."))


def parse_page(html: str, year: int, month: int) -> list[MelccfpReading]:
    """Parse a MELCCFP monthly summary HTML page.

    Returns one MelccfpReading per day that has data.  Future dates and
    fully-empty rows are skipped.
    """
    soup = BeautifulSoup(html, "html.parser")

    header_cell = soup.find(
        lambda tag: tag.name in ("th", "td") and "Jour" in tag.get_text()
    )
    if header_cell is None:
        logger.warning("Could not find 'Jour' header in MELCCFP page")
        return []

    table = header_cell.find_parent("table")
    if table is None:
        return []

    today = date.today()
    readings: list[MelccfpReading] = []

    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue

        day_text = cells[0].get_text(strip=True)
        if not day_text.isdigit():
            continue

        day = int(day_text)

        try:
            row_date = date(year, month, day)
        except ValueError:
            continue
        if row_date > today:
            continue

        # Data cells use class 'bordure_t'; 'bordure_TD' cells are spacers/flags.
        data = [c for c in cells if "bordure_t" in c.get("class", [])]
        if len(data) < 5:
            continue

        tmax = _parse_float(data[0].get_text())        # Tmax °C
        tavg = _parse_float(data[1].get_text())        # Tmoy °C
        tmin = _parse_float(data[2].get_text())        # Tmin °C
        rain = _parse_float(data[3].get_text())        # Pluie mm
        snow_cm = _parse_float(data[4].get_text())     # Neige cm
        snow = None if snow_cm is None else round(snow_cm * 10, 1)

        if all(v is None for v in (tmax, tavg, tmin, rain, snow)):
            continue

        readings.append(
            MelccfpReading(
                year=year,
                month=month,
                day=day,
                temperature_max=tmax,
                temperature_avg=tavg,
                temperature_min=tmin,
                rain=rain,
                snow=snow,
            )
        )

    return readings


async def fetch_month(
    client: httpx.AsyncClient, sensor: MelccfpSensor, year: int, month: int
) -> list[MelccfpReading]:
    """Fetch and parse one month of data for a MELCCFP sensor."""
    url = f"{BASE_URL}?cle={sensor.key}&date_selection={year:04d}-{month:02d}-01"
    response = await client.get(url)
    response.raise_for_status()
    return parse_page(response.text, year, month)


def _reading_timestamp(reading: MelccfpReading) -> datetime:
    return datetime(reading.year, reading.month, reading.day, 12, 0, 0, tzinfo=UTC)


def _to_aggregate(reading: MelccfpReading, device_id: str) -> AggregateReading:
    return AggregateReading(
        sensor=device_id,
        timestamp=_reading_timestamp(reading),
        temperature_min=reading.temperature_min,
        temperature_avg=reading.temperature_avg,
        temperature_max=reading.temperature_max,
        rain=reading.rain,
        snow=reading.snow,
    )


def write_readings(
    readings: list[MelccfpReading], device_id: str, ts_writer: TSWriter
) -> None:
    """Write MELCCFP readings to the aggregate InfluxDB measurement."""
    for r in readings:
        fields: dict[str, object] = {}
        if r.temperature_max is not None:
            fields["temperature_max"] = r.temperature_max
        if r.temperature_avg is not None:
            fields["temperature_avg"] = r.temperature_avg
        if r.temperature_min is not None:
            fields["temperature_min"] = r.temperature_min
        if r.rain is not None:
            fields["rain"] = r.rain
        if r.snow is not None:
            fields["snow"] = r.snow
        if not fields:
            continue
        ts_writer.write_point(
            AGGREGATE_MEASUREMENT,
            fields=fields,
            tags={SENSOR_TAG: device_id},
            timestamp=_reading_timestamp(r),
        )


async def publish_reading(
    reading: MelccfpReading, device_id: str, queue: Queue
) -> None:
    """Publish the most recent reading for a sensor to the SSE queue."""
    await queue.publish(
        f"weather:{device_id}", _to_aggregate(reading, device_id).model_dump_json()
    )


async def run_once(
    client: httpx.AsyncClient, ts_writer: TSWriter, queue: Queue
) -> None:
    """Fetch current month data for all MELCCFP sensors."""
    now = datetime.now(UTC)
    for sensor in SENSORS:
        readings = await fetch_month(client, sensor, now.year, now.month)
        if not readings:
            logger.warning(
                "No MELCCFP readings for %s %d-%02d",
                sensor.device_id, now.year, now.month,
            )
            continue
        write_readings(readings, sensor.device_id, ts_writer)
        await publish_reading(readings[-1], sensor.device_id, queue)
        latest = readings[-1]
        logger.info(
            "MELCCFP %s: stored %d readings for %d-%02d; "
            "latest day %d: Tmax=%s Tavg=%s Tmin=%s rain=%s snow=%s",
            sensor.device_id, len(readings), now.year, now.month,
            latest.day,
            latest.temperature_max, latest.temperature_avg, latest.temperature_min,
            latest.rain, latest.snow,
        )


async def backfill_run(
    client: httpx.AsyncClient,
    ts_writer: TSWriter,
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
) -> None:
    """Backfill historical data for all MELCCFP sensors over the given month range."""
    for sensor in SENSORS:
        year, month = from_year, from_month
        while (year, month) <= (to_year, to_month):
            logger.info("MELCCFP %s: backfilling %d-%02d", sensor.device_id, year, month)
            try:
                readings = await fetch_month(client, sensor, year, month)
                write_readings(readings, sensor.device_id, ts_writer)
                logger.info("  Wrote %d readings", len(readings))
            except Exception:
                logger.exception(
                    "MELCCFP %s: error backfilling %d-%02d",
                    sensor.device_id, year, month,
                )
            month += 1
            if month > 12:
                month = 1
                year += 1
