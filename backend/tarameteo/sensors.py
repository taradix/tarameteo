"""Sensor service reading weather points from the time series store."""

import logging
from collections.abc import Iterable, Sequence
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from math import asin, cos, floor, radians, sin, sqrt
from typing import Literal, NamedTuple

from attrs import define
from pydantic import BaseModel, Field

from tarameteo.readings import (
    AGGREGATE_MEASUREMENT,
    MEASUREMENT,
    SENSOR_TAG,
    AggregateReading,
    WeatherReading,
    from_point,
)
from tarameteo.ts import (
    TSPoint,
    TSReader,
)

SensorKind = Literal["timeseries", "aggregate"]

# Upper bound on history we scan when computing stats or listing sensors.
# Influx retention (default 7d) usually keeps this well-bounded in practice.
STATS_WINDOW = timedelta(days=90)
LATEST_LOOKBACK = timedelta(days=30)

logger = logging.getLogger(__name__)


class SensorEntry(BaseModel):
    name: str
    kind: SensorKind
    latitude: float
    longitude: float
    distance_km: float | None = Field(None, description="Distance from the queried point, if any")


class SensorList(BaseModel):
    sensors: list[SensorEntry]
    truncated: bool = Field(False, description="More sensors matched than the limit")


class Cluster(BaseModel):
    latitude: float = Field(..., description="Mean latitude of the clustered sensors")
    longitude: float = Field(..., description="Mean longitude of the clustered sensors")
    count: int
    sensor: SensorEntry | None = Field(None, description="The sensor, when the cluster holds only one")


class ClusterList(BaseModel):
    clusters: list[Cluster]


class BBox(NamedTuple):
    """Map area in degrees; west > east crosses the antimeridian."""

    west: float
    south: float
    east: float
    north: float

    def contains(self, latitude: float, longitude: float) -> bool:
        if not self.south <= latitude <= self.north:
            return False
        if self.west <= self.east:
            return self.west <= longitude <= self.east
        return longitude >= self.west or longitude <= self.east


EARTH_RADIUS_KM = 6371.0
# Grid cells per 256 px map tile, so a phone screen shows a few dozen clusters at most.
CELLS_PER_TILE = 4


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points (haversine)."""
    phi1, phi2 = radians(lat1), radians(lat2)
    a = sin((phi2 - phi1) / 2) ** 2 + cos(phi1) * cos(phi2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


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
    latitude: float
    longitude: float
    statistics: SensorStatistics


@define(frozen=True)
class SensorService:
    """Read-only view over sensor data in the time series store."""

    ts_reader: TSReader

    # NOTE: scans every sensor's last point per request; a sensor directory table replaces
    # _all_sensors past a few thousand sensors, behind the same filters.
    def list_sensors(
        self,
        *,
        names: Sequence[str] | None = None,
        q: str | None = None,
        bbox: BBox | None = None,
        near: tuple[float, float] | None = None,
        radius_km: float | None = None,
        limit: int | None = None,
    ) -> SensorList:
        """List matching sensors by name, or nearest first (within radius_km, if given) when near is given."""
        sensors = self._all_sensors()
        if names is not None:
            wanted = set(names)
            sensors = [s for s in sensors if s.name in wanted]
        if q is not None:
            sensors = [s for s in sensors if q.casefold() in s.name.casefold()]
        if bbox is not None:
            sensors = [s for s in sensors if bbox.contains(s.latitude, s.longitude)]
        if near is not None:
            for s in sensors:
                s.distance_km = distance_km(*near, s.latitude, s.longitude)
            sensors = [s for s in sensors if radius_km is None or s.distance_km <= radius_km]
            sensors.sort(key=lambda s: s.distance_km)

        if limit is not None and len(sensors) > limit:
            return SensorList(sensors=sensors[:limit], truncated=True)
        return SensorList(sensors=sensors)

    def cluster_sensors(self, bbox: BBox, zoom: int) -> ClusterList:
        """Group the sensors in bbox into grid cells sized for the map zoom level."""
        # NOTE: degree grid, not Mercator, so cells get taller toward the poles; fine for picking.
        cell = 360 / 2**zoom / CELLS_PER_TILE
        cells: dict[tuple[int, int], list[SensorEntry]] = {}
        for s in self._all_sensors():
            if bbox.contains(s.latitude, s.longitude):
                cells.setdefault((floor(s.latitude / cell), floor(s.longitude / cell)), []).append(s)
        return ClusterList(clusters=[
            Cluster(
                latitude=sum(s.latitude for s in members) / len(members),
                longitude=sum(s.longitude for s in members) / len(members),
                count=len(members),
                sensor=members[0] if len(members) == 1 else None,
            )
            for members in cells.values()
        ])

    def _all_sensors(self) -> list[SensorEntry]:
        start = datetime.now(UTC) - STATS_WINDOW
        sensors = [
            *self._list_located(MEASUREMENT, "timeseries", start),
            *self._list_located(AGGREGATE_MEASUREMENT, "aggregate", start),
        ]
        return sorted(sensors, key=lambda s: (s.name, s.kind))

    def _list_located(self, measurement: str, kind: SensorKind, start: datetime) -> list[SensorEntry]:
        # Points come oldest first, so a sensor that moved keeps its latest location.
        locations: dict[str, tuple[float, float]] = {}
        for p in self.ts_reader.last_points(measurement=measurement, start=start):
            name, lat, lon = (p.tags.get(k) for k in (SENSOR_TAG, "latitude", "longitude"))
            if name is None or lat is None or lon is None:
                logger.warning("Skipping %s series without sensor name or location: %s", measurement, p.tags)
                continue
            locations[name] = (float(lat), float(lon))
        return [
            SensorEntry(name=name, kind=kind, latitude=lat, longitude=lon)
            for name, (lat, lon) in locations.items()
        ]

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
            limit=limit,
        )
        return [from_point(p) for p in points]

    def get_latest(self, name: str) -> WeatherReading | None:
        point = self.ts_reader.latest(
            MEASUREMENT,
            tags={SENSOR_TAG: name},
            lookback=LATEST_LOOKBACK,
        )
        if point is None:
            return None
        return from_point(point)

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

    def get_weather_aggregate(
        self,
        name: str,
        *,
        start: datetime,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[AggregateReading]:
        points = self.ts_reader.query_points(
            measurement=AGGREGATE_MEASUREMENT,
            start=start,
            stop=end,
            tags={SENSOR_TAG: name},
            limit=limit,
        )
        return [from_point(p) for p in points]

    def get_sensor(self, name: str) -> SensorInfo:
        latest = self.get_latest(name)
        if latest is not None:
            return SensorInfo(
                name=name,
                latitude=latest.latitude,
                longitude=latest.longitude,
                statistics=self.get_statistics(name),
            )

        aggregate_location = self._get_latest_aggregate_location(name)
        if aggregate_location is not None:
            latitude, longitude = aggregate_location
            return SensorInfo(
                name=name,
                latitude=latitude,
                longitude=longitude,
                statistics=self.get_statistics(name),
            )

        raise ValueError(f"No readings for sensor {name!r}")

    def _get_latest_aggregate_location(self, name: str) -> tuple[float, float] | None:
        point = self.ts_reader.latest(
            AGGREGATE_MEASUREMENT,
            tags={SENSOR_TAG: name},
            lookback=LATEST_LOOKBACK,
        )
        if point is None:
            return None

        latitude = point.tags.get("latitude")
        longitude = point.tags.get("longitude")
        if latitude is None or longitude is None:
            raise ValueError(f"Missing location metadata for sensor {name!r}")
        return float(latitude), float(longitude)


def _average(points: Iterable[TSPoint], field: str) -> float | None:
    values = [p.fields[field] for p in points if p.fields.get(field) is not None]
    if not values:
        return None
    return sum(values) / len(values)
