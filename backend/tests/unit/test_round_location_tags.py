"""Unit tests for the one-off location tag migration; delete with the module."""

from datetime import (
    UTC,
    datetime,
)

from hamcrest import (
    assert_that,
    equal_to,
)

from tarameteo.round_location_tags import predicate, rounded, stale_series
from tarameteo.ts import TSPoint

TS = datetime(2026, 1, 1, tzinfo=UTC)


def point(**tags):
    return TSPoint("weather", {"temperature": 1.0}, {"device_id": "a", **tags}, TS)


def test_stale_series_finds_only_old_location_tags():
    """Only series with 6-decimal tags need rewriting; current and location-less ones don't."""
    old = point(latitude="46.810000", longitude="-71.210000")
    points = [old, point(latitude="46.8100", longitude="-71.2100"), point()]

    assert_that(stale_series(points), equal_to({
        ("weather", (("device_id", "a"), ("latitude", "46.810000"), ("longitude", "-71.210000"))): [old],
    }))


def test_rounded_rounds_to_the_nearest_4_decimals():
    """Rounding should land in the series new readings write to."""
    assert_that(
        rounded({"device_id": "a", "latitude": "46.101244", "longitude": "-75.648066"}),
        equal_to({"device_id": "a", "latitude": "46.1012", "longitude": "-75.6481"}),
    )


def test_rewriting_is_idempotent():
    """Once rewritten, a point is no longer stale, so a second run does nothing."""
    p = point(latitude="46.101244", longitude="-75.648066")
    again = TSPoint(p.measurement, p.fields, rounded(p.tags), p.timestamp)

    assert_that(stale_series([again]), equal_to({}))


def test_predicate_matches_the_series_and_escapes_quotes():
    """The delete predicate names every tag, so it can't hit another series."""
    assert_that(
        predicate("weather", [("device_id", 'a"b'), ("latitude", "46.810000")]),
        equal_to('_measurement="weather" AND device_id="a\\"b" AND latitude="46.810000"'),
    )
