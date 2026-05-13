"""METAR weather observation fetcher (Aviation Weather Center)."""

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from taraqueue import Queue

from tarameteo.sensors import (
    MEASUREMENT,
    SENSOR_TAG,
    WeatherReading,
)
from tarameteo.ts import TSWriter

logger = logging.getLogger(__name__)

BASE_URL = "https://aviationweather.gov/api/data/metar"

# Fetch 2 hours to ensure full coverage between hourly syncs.
_SYNC_HOURS = 2


@dataclass(frozen=True)
class MetarSensor:
    device_id: str
    icao_id: str


SENSORS: list[MetarSensor] = [
    MetarSensor(device_id="metar-cwmj", icao_id="CWMJ"),
    MetarSensor(device_id="metar-cyow", icao_id="CYOW"),
]

_SENSOR_BY_ICAO: dict[str, MetarSensor] = {s.icao_id: s for s in SENSORS}


@dataclass
class MetarReading:
    icao_id: str
    timestamp: datetime
    temperature: float
    humidity: float
    pressure: float  # hPa (QNH/altimeter setting)
    latitude: float
    longitude: float
    altitude: float  # metres


def _dewpoint_to_humidity(temp: float, dewp: float) -> float:
    """Compute relative humidity (%) from temperature and dew point using Magnus formula."""
    a, b = 17.625, 243.04
    return round(100.0 * math.exp(a * dewp / (b + dewp)) / math.exp(a * temp / (b + temp)), 1)


def parse_observations(observations: list[dict]) -> list[MetarReading]:
    """Parse AVW METAR JSON observations into MetarReadings.

    Skips observations with missing required fields or unknown station IDs.
    Returns readings sorted oldest-first.
    """
    readings: list[MetarReading] = []

    for obs in observations:
        icao_id = obs.get("icaoId")
        if icao_id not in _SENSOR_BY_ICAO:
            continue

        obs_time = obs.get("obsTime")
        temp = obs.get("temp")
        dewp = obs.get("dewp")
        altim = obs.get("altim")
        lat = obs.get("lat")
        lon = obs.get("lon")
        elev = obs.get("elev")

        if any(v is None for v in (obs_time, temp, dewp, altim, lat, lon, elev)):
            continue

        readings.append(
            MetarReading(
                icao_id=icao_id,
                timestamp=datetime.fromtimestamp(obs_time, tz=UTC),
                temperature=float(temp),
                humidity=_dewpoint_to_humidity(float(temp), float(dewp)),
                pressure=float(altim),
                latitude=float(lat),
                longitude=float(lon),
                altitude=float(elev),
            )
        )

    readings.sort(key=lambda r: r.timestamp)
    return readings


async def fetch_recent(
    client: httpx.AsyncClient, hours: int = _SYNC_HOURS
) -> list[MetarReading]:
    """Fetch recent METAR observations for all sensors."""
    ids = ",".join(s.icao_id for s in SENSORS)
    params = {"ids": ids, "format": "json", "hours": str(hours)}
    response = await client.get(BASE_URL, params=params)
    if response.status_code == 204:
        return []
    response.raise_for_status()
    return parse_observations(response.json())


def write_readings(
    readings: list[MetarReading], device_id: str, ts_writer: TSWriter
) -> None:
    """Write METAR readings to the weather InfluxDB measurement."""
    for r in readings:
        ts_writer.write_point(
            MEASUREMENT,
            fields={
                "temperature": r.temperature,
                "humidity": r.humidity,
                "pressure": r.pressure,
                "altitude": r.altitude,
            },
            tags={
                SENSOR_TAG: device_id,
                "latitude": f"{r.latitude:.6f}",
                "longitude": f"{r.longitude:.6f}",
            },
            timestamp=r.timestamp,
        )


def _to_weather_reading(reading: MetarReading, device_id: str) -> WeatherReading:
    return WeatherReading(
        sensor=device_id,
        timestamp=reading.timestamp,
        temperature=reading.temperature,
        humidity=reading.humidity,
        pressure=reading.pressure,
        latitude=reading.latitude,
        longitude=reading.longitude,
        altitude=reading.altitude,
    )


async def publish_reading(
    reading: MetarReading, device_id: str, queue: Queue
) -> None:
    """Publish the most recent reading for a sensor to the SSE queue."""
    await queue.publish(
        f"weather:{device_id}",
        _to_weather_reading(reading, device_id).model_dump_json(),
    )


async def run_once(
    client: httpx.AsyncClient, ts_writer: TSWriter, queue: Queue
) -> None:
    """Fetch recent METAR observations for all sensors."""
    readings = await fetch_recent(client)
    by_icao: dict[str, list[MetarReading]] = {}
    for r in readings:
        by_icao.setdefault(r.icao_id, []).append(r)

    for sensor in SENSORS:
        station_readings = by_icao.get(sensor.icao_id, [])
        if not station_readings:
            logger.warning("No METAR readings for %s", sensor.device_id)
            continue
        write_readings(station_readings, sensor.device_id, ts_writer)
        await publish_reading(station_readings[-1], sensor.device_id, queue)
        latest = station_readings[-1]
        logger.info(
            "METAR %s: stored %d readings; latest %s: T=%s H=%s P=%s",
            sensor.device_id, len(station_readings),
            latest.timestamp.isoformat(),
            latest.temperature, latest.humidity, latest.pressure,
        )


async def backfill_run(
    client: httpx.AsyncClient,
    ts_writer: TSWriter,
    from_year: int,
    from_month: int,
    to_year: int,
    to_month: int,
) -> None:
    """METAR historical backfill is not supported by the AVW API."""
    logger.warning(
        "METAR backfill is not supported; the AVW API only provides recent observations."
    )
