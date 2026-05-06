"""Sensor service reading weather points from the time series store."""

import logging
from collections.abc import Iterable
from datetime import (
    UTC,
    datetime,
    timedelta,
)

from attrs import define
from pydantic import BaseModel, Field, field_validator

from tarameteo.ts import (
    TSPoint,
    TSReader,
)

MEASUREMENT = "weather"
SENSOR_TAG = "device_id"

# Upper bound on history we scan when computing stats or listing sensors.
# Influx retention (default 7d) usually keeps this well-bounded in practice.
STATS_WINDOW = timedelta(days=90)
LATEST_LOOKBACK = "30d"

_MIN_TIMESTAMP = datetime(2020, 1, 1, tzinfo=UTC)

logger = logging.getLogger(__name__)


class WeatherReading(BaseModel):
    """A single weather measurement."""

    sensor: str = Field(..., description="Sensor name")
    timestamp: datetime | int = Field(..., description="Timestamp of reading")
    temperature: float = Field(..., description="Temperature in Celsius")
    humidity: float = Field(..., description="Humidity percentage")
    pressure: float = Field(..., description="Pressure in hPa")
    altitude: float | None = Field(None, description="Altitude in meters")
    rssi: int | None = Field(None, description="WiFi RSSI in dBm")
    retry_count: int | None = Field(None, description="Number of retry attempts")

    @field_validator("timestamp", mode="before")
    @classmethod
    def coerce_timestamp(cls, v: object) -> datetime:
        if isinstance(v, int):
            v = datetime.fromtimestamp(v, tz=UTC)
        if isinstance(v, datetime) and v < _MIN_TIMESTAMP:
            logger.warning("Firmware sent invalid timestamp %s (NTP sync likely failed); using server time", v)
            return datetime.now(UTC)
        return v  # type: ignore[return-value]


class SensorStatistics(BaseModel):
    """Aggregated statistics over the stats window."""

    total_readings: int
    first_reading: datetime | None
    last_reading: datetime | None
    last_24h_readings: int
    average_temperature: float | None
    average_humidity: float | None
    average_pressure: float | None
    average_rssi: int | None


class SensorInfo(BaseModel):
    """Full sensor record returned by GET /api/sensors/{name}."""

    name: str
    statistics: SensorStatistics


@define(frozen=True)
class SensorService:
    """Read-only view over sensor data in the time series store."""

    ts_reader: TSReader

    def list_sensors(self) -> list[str]:
        start = datetime.now(UTC) - STATS_WINDOW
        return self.ts_reader.list_tag_values(
            measurement=MEASUREMENT,
            tag_key=SENSOR_TAG,
            start=start,
        )

    def get_weather(
        self,
        name: str,
        *,
        start: datetime,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[WeatherReading]:
        points = self.ts_reader.query_points(
            measurement=MEASUREMENT,
            start=start,
            stop=end,
            tags={SENSOR_TAG: name},
        )
        if limit is not None:
            points = points[:limit]
        return [self._to_reading(name, p) for p in points]

    def get_latest(self, name: str) -> WeatherReading | None:
        point = self.ts_reader.latest(
            MEASUREMENT,
            tags={SENSOR_TAG: name},
            lookback=LATEST_LOOKBACK,
        )
        if point is None:
            return None
        return self._to_reading(name, point)

    def get_statistics(self, name: str) -> SensorStatistics:
        now = datetime.now(UTC)
        points = self.ts_reader.query_points(
            measurement=MEASUREMENT,
            start=now - STATS_WINDOW,
            tags={SENSOR_TAG: name},
        )
        if not points:
            return SensorStatistics(
                total_readings=0,
                first_reading=None,
                last_reading=None,
                last_24h_readings=0,
                average_temperature=None,
                average_humidity=None,
                average_pressure=None,
                average_rssi=None,
            )

        cutoff = now - timedelta(hours=24)
        recent = [p for p in points if p.timestamp >= cutoff]

        rssi_avg = _average(recent, "rssi")
        return SensorStatistics(
            total_readings=len(points),
            first_reading=points[0].timestamp,
            last_reading=points[-1].timestamp,
            last_24h_readings=len(recent),
            average_temperature=_average(recent, "temperature"),
            average_humidity=_average(recent, "humidity"),
            average_pressure=_average(recent, "pressure"),
            average_rssi=round(rssi_avg) if rssi_avg is not None else None,
        )

    def get_sensor(self, name: str) -> SensorInfo:
        return SensorInfo(name=name, statistics=self.get_statistics(name))

    @staticmethod
    def _to_reading(sensor: str, point: TSPoint) -> WeatherReading:
        f = point.fields
        return WeatherReading(
            sensor=sensor,
            timestamp=point.timestamp,
            temperature=float(f["temperature"]),
            humidity=float(f["humidity"]),
            pressure=float(f["pressure"]),
            altitude=_opt_float(f.get("altitude")),
            rssi=_opt_int(f.get("rssi")),
            retry_count=_opt_int(f.get("retry_count")),
        )


def _average(points: Iterable[TSPoint], field: str) -> float | None:
    values = [p.fields[field] for p in points if p.fields.get(field) is not None]
    if not values:
        return None
    return sum(values) / len(values)


def _opt_float(v: object) -> float | None:
    return None if v is None else float(v)  # type: ignore[arg-type]


def _opt_int(v: object) -> int | None:
    return None if v is None else int(v)  # type: ignore[arg-type]
