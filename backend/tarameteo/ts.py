"""Time series abstraction and implementation."""

import os
import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from itertools import count
from time import sleep
from typing import (
    Any,
    Literal,
    Protocol,
)

from attrs import (
    define,
    field,
)
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.flux_table import FluxRecord, FluxTable
from influxdb_client.client.query_api import QueryApi
from influxdb_client.client.write_api import SYNCHRONOUS
from more_itertools import chunked

Scalar = int | float | bool | str
Aggregate = Literal["mean", "min", "max", "sum", "count", "last", "first"]


@define(frozen=True)
class TSPoint:

    measurement: str
    fields: Mapping[str, Scalar]
    tags: Mapping[str, str] = field(factory=dict)
    timestamp: datetime = field(factory=lambda: datetime.now(UTC))


class TSReader(Protocol):

    def query_points(
        self,
        *,
        measurement: str,
        start: datetime,
        stop: datetime | None = None,
        tags: Mapping[str, str] | None = None,
        fields: Sequence[str] | None = None,
        every: str | None = None,
        aggregate: Aggregate | None = None,
    ) -> list[TSPoint]:
        """Return points in ascending timestamp order."""

    def latest(
        self,
        measurement: str,
        *,
        tags: Mapping[str, str] | None = None,
        fields: Sequence[str] | None = None,
        lookback: str | None = None,
    ) -> TSPoint | None:
        """Return the most recent point for the series."""

    def list_tag_values(
        self,
        *,
        measurement: str,
        tag_key: str,
        start: datetime | None = None,
        stop: datetime | None = None,
        contains: str | None = None,
        limit: int = 1000,
    ) -> list[str]:
        """Convenience for populating UI dropdowns."""


class TSWriter(Protocol):

    def write_point(
        self,
        measurement: str,
        fields: Mapping[str, Scalar],
        tags: Mapping[str, str] | None = None,
        timestamp: datetime | None= None,
    ) -> None:
        if fields is None:
            fields = {}
        if timestamp is None:
            timestamp = datetime.now(UTC)

        point = TSPoint(
            measurement=measurement,
            fields=fields,
            tags=tags,
            timestamp=timestamp,
        )
        self.write_points([point])

    def write_points(self, points: Sequence[TSPoint]) -> None:
        """Write points to a timeseries."""


@define(frozen=True)
class InfluxReader(TSReader):
    """Reader for InfluxDB operations."""

    query_api: QueryApi
    org: str
    bucket: str
    batch_size: int = 5_000
    max_retries: int = 3
    retry_backoff_seconds: float = 0.5

    @classmethod
    def from_env(cls, env=os.environ) -> "InfluxReader":
        return cls.from_url(
            url=env["INFLUX_URL"],
            token=env["INFLUX_TOKEN"],
            org=env["INFLUX_ORG"],
            bucket=env["INFLUX_BUCKET"],
        )

    @classmethod
    def from_url(cls, url: str, token: str, org: str, bucket: str) -> "InfluxReader":
        client = InfluxDBClient(
            url=url,
            token=token,
            timeout=30_000  # 30 second timeout
        )
        query_api = client.query_api()
        return cls(
            query_api=query_api,
            org=org,
            bucket=bucket,
        )

    def query_points(
        self,
        *,
        measurement: str,
        start: datetime,
        stop: datetime | None = None,
        tags: Mapping[str, str] | None = None,
        fields: Sequence[str] | None = None,
        every: str | None = None,
        aggregate: Aggregate | None = None,
    ) -> list[TSPoint]:
        flux, params = self._build_points_query(
            measurement=measurement,
            start=start,
            stop=stop,
            tags=tags,
            fields=fields,
            every=every,
            aggregate=aggregate,
        )
        records = self._query_records(flux, params=params)
        return self._records_to_points(records)

    def latest(
        self,
        measurement: str,
        *,
        tags: Mapping[str, str] | None = None,
        fields: Sequence[str] | None = None,
        lookback: str | None = None,
    ) -> TSPoint | None:
        # Use a bounded range by default to avoid scanning too much.
        # If no lookback provided, pick something conservative.
        lookback = lookback or "1h"

        flux, params = self._build_latest_query(
            measurement=measurement,
            lookback=lookback,
            tags=tags,
            fields=fields,
        )
        records = self._query_records(flux, params=params)
        points = self._records_to_points(records)

        # We might get multiple timestamps if different fields last-updated at slightly different times.
        # Choose the newest timestamp point.
        if not points:
            return None
        return max(points, key=lambda p: p.timestamp)

    def list_tag_values(
        self,
        *,
        measurement: str,
        tag_key: str,
        start: datetime | None = None,
        stop: datetime | None = None,
        contains: str | None = None,
        limit: int = 1000,
    ) -> list[str]:
        if limit <= 0:
            return []

        flux, params = self._build_tag_values_query(
            measurement=measurement,
            tag_key=tag_key,
            start=start,
            stop=stop,
            contains=contains,
            limit=limit,
        )
        records = self._query_records(flux, params=params)

        # We arrange the query so the tag value is in a column named "value"
        vals = []
        for r in records:
            v = r.values.get("value")
            if isinstance(v, str):
                vals.append(v)
        # Dedup while preserving order
        seen = set()
        out = []
        for v in vals:
            if v not in seen:
                seen.add(v)
                out.append(v)
        return out

    def _query_tables(self, flux: str, *, params: Mapping[str, Any]) -> list[FluxTable]:
        for attempt in count():
            try:
                return self.query_api.query(query=flux, org=self.org, params=dict(params))
            except Exception:
                if attempt >= self.max_retries:
                    raise

                # exponential backoff: base * 2^attempt
                sleep(self.retry_backoff_seconds * (2 ** attempt))

    def _query_records(self, flux: str, *, params: Mapping[str, Any]) -> list[FluxRecord]:
        tables = self._query_tables(flux, params=params)
        return [r for t in tables for r in t.records]

    def _build_points_query(
        self,
        *,
        measurement: str,
        start: datetime,
        stop: datetime | None,
        tags: Mapping[str, str] | None,
        fields: Sequence[str] | None,
        every: str | None,
        aggregate: Aggregate | None,
    ) -> tuple[str, dict[str, Any]]:
        params = {
            "bucket": self.bucket,
            "measurement": measurement,
            "start": start,
        }
        if stop is not None:
            params["stop"] = stop

        flux_lines = [
            'from(bucket: bucket)',
            '  |> range(start: start' + (', stop: stop' if stop is not None else '') + ')',
            '  |> filter(fn: (r) => r._measurement == measurement)',
        ]

        if tags:
            # param keys: tag_<name>
            for k, v in tags.items():
                p = f"tag_{k}"
                params[p] = str(v)
                flux_lines.append(f'  |> filter(fn: (r) => r["{k}"] == {p})')

        if fields:
            # Build an OR expression with parameters field_0, field_1...
            ors = []
            for i, f in enumerate(fields):
                p = f"field_{i}"
                params[p] = str(f)
                ors.append(f'r._field == {p}')
            expr = " or ".join(ors)
            flux_lines.append(f'  |> filter(fn: (r) => {expr})')

        if every:
            # Aggregation is optional; if you specify every without aggregate, default to mean.
            agg = aggregate or "mean"
            params["every"] = every
            params["aggregate"] = agg
            # aggregateWindow requires fn identifier, not a string, so we map aggregate to fn literal.
            # Safe because aggregate is from a Literal union.
            flux_lines.append(f'  |> aggregateWindow(every: every, fn: {agg}, createEmpty: false)')

        flux = "\n".join(flux_lines)
        return flux, params

    def _build_latest_query(
        self,
        *,
        measurement: str,
        lookback: str,
        tags: Mapping[str, str] | None,
        fields: Sequence[str] | None,
    ) -> tuple[str, dict[str, Any]]:
        params = {
            "bucket": self.bucket,
            "measurement": measurement,
            "lookback": lookback,
        }

        flux_lines = [
            'from(bucket: bucket)',
            '  |> range(start: -duration(v: lookback))',
            '  |> filter(fn: (r) => r._measurement == measurement)',
        ]

        if tags:
            for k, v in tags.items():
                p = f"tag_{k}"
                params[p] = str(v)
                flux_lines.append(f'  |> filter(fn: (r) => r["{k}"] == {p})')

        if fields:
            ors = []
            for i, f in enumerate(fields):
                p = f"field_{i}"
                params[p] = str(f)
                ors.append(f'r._field == {p}')
            flux_lines.append(f'  |> filter(fn: (r) => {" or ".join(ors)})')

        # "last()" works per series; this returns one row per field.
        flux_lines.append('  |> last()')

        flux = "\n".join(flux_lines)
        return flux, params

    def _build_tag_values_query(
        self,
        *,
        measurement: str,
        tag_key: str,
        start: datetime | None,
        stop: datetime | None,
        contains: str | None,
        limit: int,
    ) -> tuple[str, dict[str, Any]]:
        params = {
            "bucket": self.bucket,
            "measurement": measurement,
            "tag_key": tag_key,
            "limit": limit,
        }
        if start is not None:
            params["start"] = start
        if stop is not None:
            params["stop"] = stop
        if contains is not None:
            params["contains"] = contains

        # We can use schema.tagValues (requires the "influxdata/influxdb/schema" package).
        # This is convenient and efficient for listing tag values.
        flux_lines = [
            'import "influxdata/influxdb/schema"',
            'schema.tagValues(',
            '  bucket: bucket,',
            '  tag: tag_key,',
            # Optional time bounds:
            ('  start: start,' if start is not None else ''),
            ('  stop: stop,' if stop is not None else ''),
            '  predicate: (r) => r._measurement == measurement,',
            ')',
        ]
        flux_lines = [ln for ln in flux_lines if ln]  # drop empty lines

        if contains is not None:
            # Filter returned tag values (column is "value")
            flux_lines.append('  |> filter(fn: (r) => containsStr(v: r.value, substr: contains))')

        flux_lines.append('  |> limit(n: limit)')
        flux = "\n".join(flux_lines)
        return flux, params

    @staticmethod
    def _records_to_points(records: Sequence[FluxRecord]) -> list[TSPoint]:  # noqa: C901
        """
        Influx results are "tall" (one row per field).
        Reconstruct "wide" TSPoint by grouping on (_measurement, _time, tags...).
        """
        system_cols = {
            "result",
            "table",
            "_start",
            "_stop",
            "_time",
            "_value",
            "_field",
            "_measurement",
        }

        def infer_tags(vals: Mapping[str, Any]) -> dict[str, str]:
            tags = {}
            for k, v in vals.items():
                if k in system_cols:
                    continue
                if isinstance(v, str):
                    tags[k] = v
            return tags

        groups = {}

        for r in records:
            vals = r.values
            m = vals.get("_measurement")
            t = vals.get("_time")
            f = vals.get("_field")
            v = vals.get("_value")

            if m is None or t is None or f is None:
                continue
            if not isinstance(t, datetime):
                # best-effort parse
                with suppress(Exception):
                    t = datetime.fromisoformat(str(t))

            tags = infer_tags(vals)
            key = (str(m), t, tuple(sorted(tags.items())))

            g = groups.get(key)
            if g is None:
                g = {"measurement": str(m), "timestamp": t, "tags": tags, "fields": {}}
                groups[key] = g

            g["fields"][str(f)] = v

        points: list[TSPoint] = []
        for g in groups.values():
            fields = dict(g["fields"])
            if not fields:
                continue
            points.append(
                TSPoint(
                    measurement=g["measurement"],
                    timestamp=g["timestamp"],
                    tags=g["tags"],
                    fields=fields,
                )
            )
        points.sort(key=lambda p: p.timestamp)
        return points


@define(frozen=True)
class InfluxWriter(TSWriter):
    """Writer for InfluxDB operations."""

    write_api: object  # WriteApi from influxdb_client
    org: str
    bucket: str
    batch_size: int = 5_000
    max_retries: int = 3
    retry_backoff_seconds: float = 0.5

    @classmethod
    def from_env(cls, env=os.environ) -> "InfluxWriter":
        return cls.from_url(
            url=env["INFLUX_URL"],
            token=env["INFLUX_TOKEN"],
            org=env["INFLUX_ORG"],
            bucket=env["INFLUX_BUCKET"],
        )

    @classmethod
    def from_url(cls, url: str, token: str, org: str, bucket: str) -> "InfluxWriter":
        client = InfluxDBClient(
            url=url,
            token=token,
            org=org,
            timeout=30_000  # 30 second timeout
        )
        write_api = client.write_api(write_options=SYNCHRONOUS)
        return cls(
            write_api=write_api,
            org=org,
            bucket=bucket,
        )

    def write_points(self, points: Sequence[TSPoint]) -> None:
        influx_points = [self._to_influx_point(p) for p in points]
        self.write_influx_points(influx_points)

    def write_influx_points(self, points: Sequence[Point]) -> None:
        for chunk in chunked(points, self.batch_size):
            self._write_with_retries(chunk)

    def _to_influx_point(self, p: TSPoint) -> Point:
        ip = Point(p.measurement)

        for k, v in p.tags.items():
            if v is not None:
                ip.tag(str(k), v)

        if not p.fields:
            raise ValueError("Influx requires at least one field")
        for k, v in p.fields.items():
            if v is not None:
                ip.field(str(k), v)

        if p.timestamp:
            ip.time(p.timestamp)

        return ip

    def _write_with_retries(self, batch: Sequence[Point]) -> None:
        for attempt in count():
            try:
                return self.write_api.write(bucket=self.bucket, org=self.org, record=batch)
            except Exception:
                if attempt >= self.max_retries:
                    raise

                # exponential backoff: base * 2^attempt
                sleep(self.retry_backoff_seconds * (2 ** attempt))


_DURATION_UNITS = {
    "ns": timedelta(microseconds=0.001),
    "us": timedelta(microseconds=1),
    "ms": timedelta(milliseconds=1),
    "s": timedelta(seconds=1),
    "m": timedelta(minutes=1),
    "h": timedelta(hours=1),
    "d": timedelta(days=1),
    "w": timedelta(weeks=1),
}


def _parse_duration(s: str) -> timedelta:
    match = re.fullmatch(r"\s*(\d+)\s*([a-z]+)\s*", s)
    if not match:
        raise ValueError(f"Invalid duration: {s!r}")
    n, unit = int(match.group(1)), match.group(2)
    if unit not in _DURATION_UNITS:
        raise ValueError(f"Unknown duration unit: {unit!r}")
    return _DURATION_UNITS[unit] * n


@define
class MemoryStore:
    """Shared in-memory backing store for MemoryReader and MemoryWriter."""

    points: list[TSPoint] = field(factory=list)


@define(frozen=True)
class MemoryReader(TSReader):
    """In-memory TSReader for tests."""

    store: MemoryStore

    def query_points(
        self,
        *,
        measurement: str,
        start: datetime,
        stop: datetime | None = None,
        tags: Mapping[str, str] | None = None,
        fields: Sequence[str] | None = None,
        every: str | None = None,
        aggregate: Aggregate | None = None,
    ) -> list[TSPoint]:
        matched = [
            p for p in self.store.points
            if p.measurement == measurement
            and p.timestamp >= start
            and (stop is None or p.timestamp < stop)
            and _tags_match(p.tags, tags)
        ]
        if fields:
            matched = [
                TSPoint(
                    measurement=p.measurement,
                    fields={k: v for k, v in p.fields.items() if k in fields},
                    tags=p.tags,
                    timestamp=p.timestamp,
                )
                for p in matched
            ]
            matched = [p for p in matched if p.fields]
        matched.sort(key=lambda p: p.timestamp)
        return matched

    def latest(
        self,
        measurement: str,
        *,
        tags: Mapping[str, str] | None = None,
        fields: Sequence[str] | None = None,
        lookback: str | None = None,
    ) -> TSPoint | None:
        start = datetime.now(UTC) - _parse_duration(lookback or "1h")
        points = self.query_points(
            measurement=measurement,
            start=start,
            tags=tags,
            fields=fields,
        )
        return points[-1] if points else None

    def list_tag_values(
        self,
        *,
        measurement: str,
        tag_key: str,
        start: datetime | None = None,
        stop: datetime | None = None,
        contains: str | None = None,
        limit: int = 1000,
    ) -> list[str]:
        if limit <= 0:
            return []

        seen: set[str] = set()
        out: list[str] = []
        for p in self.store.points:
            if p.measurement != measurement:
                continue
            if start is not None and p.timestamp < start:
                continue
            if stop is not None and p.timestamp >= stop:
                continue
            v = p.tags.get(tag_key)
            if v is None or v in seen:
                continue
            if contains is not None and contains not in v:
                continue
            seen.add(v)
            out.append(v)
            if len(out) >= limit:
                break
        return out


@define(frozen=True)
class MemoryWriter(TSWriter):
    """In-memory TSWriter for tests."""

    store: MemoryStore

    def write_point(
        self,
        measurement: str,
        fields: Mapping[str, Scalar],
        tags: Mapping[str, str] | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        point = TSPoint(
            measurement=measurement,
            fields=dict(fields),
            tags=dict(tags) if tags else {},
            timestamp=timestamp or datetime.now(UTC),
        )
        self.write_points([point])

    def write_points(self, points: Sequence[TSPoint]) -> None:
        self.store.points.extend(points)


def _tags_match(point_tags: Mapping[str, str], wanted: Mapping[str, str] | None) -> bool:
    if not wanted:
        return True
    return all(point_tags.get(k) == v for k, v in wanted.items())
