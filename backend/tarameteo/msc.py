"""MSC (Meteorological Service of Canada) hourly climate station fetcher."""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from taraqueue import Queue

from tarameteo.sensors import (
    MEASUREMENT,
    SENSOR_TAG,
    WeatherReading,
)
from tarameteo.ts import TSWriter

logger = logging.getLogger(__name__)

BASE_URL = "https://api.weather.gc.ca/collections/climate-hourly/items"

# Max hours in a month (31 days × 24 hours).
_MONTH_LIMIT = 744


@dataclass(frozen=True)
class MscSensor:
    device_id: str
    station_id: str


SENSORS: list[MscSensor] = [
    MscSensor(device_id="msc-mont-laurier", station_id="7035160"),
    MscSensor(device_id="msc-maniwaki-airport", station_id="7034482"),
]


@dataclass
class MscReading:
    utc_timestamp: datetime
    temperature: float
    humidity: float
    pressure: float  # hPa
    latitude: float
    longitude: float
    rain: float | None


def _opt_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


def parse_features(features: list[dict], year: int, month: int) -> list[MscReading]:
    """Parse GeoMet climate-hourly API features into MscReadings.

    Returns one MscReading per hour that has all required fields present.
    Future timestamps are skipped.
    """
    now = datetime.now(UTC)
    readings: list[MscReading] = []

    for feat in features:
        props = feat.get("properties", {})

        day = props.get("LOCAL_DAY")
        if not isinstance(day, int):
            continue
        try:
            date(year, month, day)
        except ValueError:
            continue

        utc_str = props.get("UTC_DATE")
        if not utc_str:
            continue
        try:
            utc_ts = datetime.fromisoformat(utc_str).replace(tzinfo=UTC)
        except ValueError:
            continue
        if utc_ts > now:
            continue

        temp = _opt_float(props.get("TEMP"))
        humidity = _opt_float(props.get("RELATIVE_HUMIDITY"))
        pressure_kpa = _opt_float(props.get("STATION_PRESSURE"))
        lat = _opt_float(props.get("LATITUDE_DECIMAL_DEGREES"))
        lon = _opt_float(props.get("LONGITUDE_DECIMAL_DEGREES"))

        if any(v is None for v in (temp, humidity, pressure_kpa, lat, lon)):
            continue

        readings.append(
            MscReading(
                utc_timestamp=utc_ts,
                temperature=temp,  # type: ignore[arg-type]
                humidity=humidity,  # type: ignore[arg-type]
                pressure=round(pressure_kpa * 10, 2),  # kPa → hPa  # type: ignore[operator]
                latitude=lat,  # type: ignore[arg-type]
                longitude=lon,  # type: ignore[arg-type]
                rain=_opt_float(props.get("PRECIP_AMOUNT")),
            )
        )

    return readings


async def fetch_month(
    client: httpx.AsyncClient, sensor: MscSensor, year: int, month: int
) -> list[MscReading]:
    """Fetch and parse one month of hourly data for an MSC station."""
    params = {
        "CLIMATE_IDENTIFIER": sensor.station_id,
        "LOCAL_YEAR": str(year),
        "LOCAL_MONTH": str(month),
        "limit": str(_MONTH_LIMIT),
        "f": "json",
    }
    response = await client.get(BASE_URL, params=params)
    response.raise_for_status()
    data = response.json()
    return parse_features(data.get("features", []), year, month)


def write_readings(
    readings: list[MscReading], device_id: str, ts_writer: TSWriter
) -> None:
    """Write MSC hourly readings to the weather InfluxDB measurement."""
    for r in readings:
        fields: dict[str, object] = {
            "temperature": r.temperature,
            "humidity": r.humidity,
            "pressure": r.pressure,
        }
        if r.rain is not None:
            fields["rain"] = r.rain
        ts_writer.write_point(
            MEASUREMENT,
            fields=fields,
            tags={
                SENSOR_TAG: device_id,
                "latitude": f"{r.latitude:.6f}",
                "longitude": f"{r.longitude:.6f}",
            },
            timestamp=r.utc_timestamp,
        )


def _to_weather_reading(reading: MscReading, device_id: str) -> WeatherReading:
    return WeatherReading(
        sensor=device_id,
        timestamp=reading.utc_timestamp,
        temperature=reading.temperature,
        humidity=reading.humidity,
        pressure=reading.pressure,
        latitude=reading.latitude,
        longitude=reading.longitude,
        rain=reading.rain,
    )


async def publish_reading(
    reading: MscReading, device_id: str, queue: Queue
) -> None:
    """Publish the most recent reading for a sensor to the SSE queue."""
    await queue.publish(
        f"weather:{device_id}",
        _to_weather_reading(reading, device_id).model_dump_json(),
    )


async def run_once(
    client: httpx.AsyncClient, ts_writer: TSWriter, queue: Queue
) -> None:
    """Fetch current month hourly data for all MSC sensors."""
    now = datetime.now(UTC)
    for sensor in SENSORS:
        readings = await fetch_month(client, sensor, now.year, now.month)
        if not readings:
            logger.warning(
                "No MSC readings for %s %d-%02d",
                sensor.device_id, now.year, now.month,
            )
            continue
        write_readings(readings, sensor.device_id, ts_writer)
        await publish_reading(readings[-1], sensor.device_id, queue)
        latest = readings[-1]
        logger.info(
            "MSC %s: stored %d readings for %d-%02d; "
            "latest %s: T=%s H=%s P=%s rain=%s",
            sensor.device_id, len(readings), now.year, now.month,
            latest.utc_timestamp.isoformat(),
            latest.temperature, latest.humidity, latest.pressure, latest.rain,
        )


async def backfill_run(
    client: httpx.AsyncClient,
    ts_writer: TSWriter,
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
) -> None:
    """Backfill historical hourly data for all MSC sensors over the given month range."""
    for sensor in SENSORS:
        year, month = from_year, from_month
        while (year, month) <= (to_year, to_month):
            logger.info("MSC %s: backfilling %d-%02d", sensor.device_id, year, month)
            try:
                readings = await fetch_month(client, sensor, year, month)
                write_readings(readings, sensor.device_id, ts_writer)
                logger.info("  Wrote %d readings", len(readings))
            except Exception:
                logger.exception(
                    "MSC %s: error backfilling %d-%02d",
                    sensor.device_id, year, month,
                )
            month += 1
            if month > 12:
                month = 1
                year += 1
