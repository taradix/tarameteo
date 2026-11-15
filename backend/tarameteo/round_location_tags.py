"""One-off: rewrite location tags in the current 4-decimal format, then delete the old series.

Run it after deploying the 4-decimal tags, with --dry-run first:

    docker compose exec api python -m tarameteo.round_location_tags --dry-run

Safe to run again: a series is deleted only after its points are rewritten, and rewriting a
point overwrites it. Delete this module once production is migrated.
"""

import os
from argparse import ArgumentParser
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from influxdb_client import InfluxDBClient

from tarameteo.readings import AGGREGATE_MEASUREMENT, MEASUREMENT, location_tags
from tarameteo.ts import InfluxReader, InfluxWriter, TSPoint

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

Series = tuple[str, tuple[tuple[str, str], ...]]


def rounded(tags: Mapping[str, str]) -> dict[str, str]:
    """The tags with the location in the current format, or as they are without a location."""
    if "latitude" not in tags or "longitude" not in tags:
        return dict(tags)
    return {**tags, **location_tags(float(tags["latitude"]), float(tags["longitude"]))}


def stale_series(points: Iterable[TSPoint]) -> dict[Series, list[TSPoint]]:
    """Points whose location tags aren't in the current format, by series."""
    series: dict[Series, list[TSPoint]] = {}
    for p in points:
        if rounded(p.tags) != p.tags:
            series.setdefault((p.measurement, tuple(sorted(p.tags.items()))), []).append(p)
    return series


def predicate(measurement: str, tags: Iterable[tuple[str, str]]) -> str:
    """Influx delete predicate matching exactly one series."""
    terms = [("_measurement", measurement), *tags]
    return " AND ".join(f'{k}="{v.replace('"', '\\"')}"' for k, v in terms)


def main(argv=None, env=os.environ) -> None:
    parser = ArgumentParser(prog="python -m tarameteo.round_location_tags")
    parser.add_argument("--dry-run", action="store_true", help="Only list the series that would be rewritten")
    args = parser.parse_args(argv)

    reader, writer = InfluxReader.from_env(env), InfluxWriter.from_env(env)
    client = InfluxDBClient(url=env["INFLUX_URL"], token=env["INFLUX_TOKEN"], org=env["INFLUX_ORG"])
    for measurement in (MEASUREMENT, AGGREGATE_MEASUREMENT):
        # NOTE: reads the whole measurement at once; fine within Influx retention, go per sensor if backfills grow.
        points = reader.query_points(measurement=measurement, start=_EPOCH)
        for (name, tags), series in stale_series(points).items():
            print(f"{name} {dict(tags)}: {len(series)} points -> {rounded(dict(tags))}")
            if args.dry_run:
                continue
            writer.write_points([
                TSPoint(measurement=p.measurement, fields=p.fields, tags=rounded(p.tags), timestamp=p.timestamp)
                for p in series
            ])
            client.delete_api().delete(
                _EPOCH, datetime.now(UTC), predicate(name, tags), bucket=env["INFLUX_BUCKET"], org=env["INFLUX_ORG"],
            )


if __name__ == "__main__":
    main()
