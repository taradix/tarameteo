"""Weather readings and how they are stored in the time series store."""

import logging
from datetime import (
    UTC,
    datetime,
)

from pydantic import BaseModel, Field, model_validator

from tarameteo.ts import TSPoint

MEASUREMENT = "weather"
AGGREGATE_MEASUREMENT = "weather_aggregate"
SENSOR_TAG = "device_id"
LABEL_TAG = "label"
LABEL_MAX_LENGTH = 32

_MIN_TIMESTAMP = datetime(2020, 1, 1, tzinfo=UTC)

logger = logging.getLogger(__name__)


class WeatherReading(BaseModel):
    """A single weather measurement."""

    sensor: str = Field(..., description="Sensor name")
    # No control characters: the label goes into email subjects.
    label: str | None = Field(
        None, min_length=1, max_length=LABEL_MAX_LENGTH, pattern=r"^[^\x00-\x1f\x7f]+$",
        description="The owner's name for the sensor",
    )
    timestamp: datetime = Field(..., description="Timestamp of reading")
    temperature: float = Field(..., description="Temperature in Celsius")
    humidity: float = Field(..., description="Humidity percentage")
    pressure: float = Field(..., description="Pressure in hPa")
    latitude: float = Field(..., description="Sensor latitude")
    longitude: float = Field(..., description="Sensor longitude")
    altitude: float | None = Field(None, description="Altitude in meters")
    rain: float | None = Field(None, description="Rainfall in mm")
    snow: float | None = Field(None, description="Snowfall in mm")
    rssi: int | None = Field(None, description="WiFi RSSI in dBm")
    retry_count: int | None = Field(None, description="Number of retry attempts")
    # From TaraMeteo stations only, like retry_count; the 64 bytes of their version buffers.
    board: str | None = Field(None, max_length=64, description="Board the station's firmware is built for")
    firmware: str | None = Field(None, max_length=64, description="Firmware version the station runs")
    firmware_failed: str | None = Field(
        None, max_length=64, description="Last firmware version that failed to install, when one did",
    )
    server_time: datetime | None = Field(
        None,
        exclude=True,
        description="Fallback time when firmware timestamp is invalid (default: now)",
    )

    @model_validator(mode="before")
    @classmethod
    def coerce_timestamp(cls, data: dict) -> dict:
        """Coerce integer timestamps and fall back to server time for invalid timestamps."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, int):
            timestamp = datetime.fromtimestamp(timestamp, tz=UTC)
        if isinstance(timestamp, datetime) and timestamp < _MIN_TIMESTAMP:
            server_time = data.get("server_time") or datetime.now(UTC)
            logger.warning("Firmware sent invalid timestamp %s (NTP sync likely failed); using server time", timestamp)
            data["timestamp"] = server_time
        elif isinstance(timestamp, datetime):
            data["timestamp"] = timestamp
        return data


class AggregateReading(BaseModel):
    """A period aggregate (min/avg/max) weather measurement."""

    sensor: str
    label: str | None = None
    timestamp: datetime
    latitude: float | None = None
    longitude: float | None = None
    temperature_min: float | None = None
    temperature_avg: float | None = None
    temperature_max: float | None = None
    humidity_min: float | None = None
    humidity_avg: float | None = None
    humidity_max: float | None = None
    pressure_min: float | None = None
    pressure_avg: float | None = None
    pressure_max: float | None = None
    rain: float | None = None
    snow: float | None = None


Reading = WeatherReading | AggregateReading


def location_tags(latitude: float, longitude: float) -> dict[str, str]:
    """Location tags at 4 decimals (about 11 m), so a position that wanders a little stays one series."""
    # NOTE: lat/lon are tags, so each move is a new series; fine for provisioned locations,
    # make them fields if a GPS source ever sends positions that wander more than this.
    return {"latitude": f"{latitude:.4f}", "longitude": f"{longitude:.4f}"}


def to_point(reading: Reading) -> TSPoint:
    """Map a reading to its Influx point: label and location as tags, measurements as fields."""
    tags = {SENSOR_TAG: reading.sensor}
    if reading.label is not None:
        tags[LABEL_TAG] = reading.label
    if reading.latitude is not None and reading.longitude is not None:
        tags |= location_tags(reading.latitude, reading.longitude)
    return TSPoint(
        measurement=MEASUREMENT if isinstance(reading, WeatherReading) else AGGREGATE_MEASUREMENT,
        fields=reading.model_dump(exclude={"sensor", "label", "timestamp", "latitude", "longitude"}, exclude_none=True),
        tags=tags,
        timestamp=reading.timestamp,
    )


def from_point(point: TSPoint) -> Reading:
    """Map an Influx point back to its reading, the reverse of to_point."""
    model = WeatherReading if point.measurement == MEASUREMENT else AggregateReading
    return model(
        sensor=point.tags[SENSOR_TAG],
        label=point.tags.get(LABEL_TAG),
        timestamp=point.timestamp,
        latitude=point.tags.get("latitude"),
        longitude=point.tags.get("longitude"),
        **point.fields,
    )
