"""Unit tests for the MemoryReader and MemoryWriter."""

from datetime import (
    UTC,
    datetime,
    timedelta,
)

from hamcrest import (
    assert_that,
    contains_exactly,
    contains_inanyorder,
    empty,
    has_properties,
    none,
)

from tarameteo.ts import TSPoint


def test_memory_writer_write_point(memory_store, memory_writer):
    """Writing a point should store it in the shared store."""
    ts = datetime(2026, 1, 1, tzinfo=UTC)

    memory_writer.write_point(
        "weather", {"temperature": 20.0}, tags={"device_id": "a"}, timestamp=ts,
    )

    assert_that(memory_store.points, contains_exactly(
        has_properties(
            measurement="weather",
            fields={"temperature": 20.0},
            tags={"device_id": "a"},
            timestamp=ts,
        ),
    ))


def test_memory_writer_write_points(memory_store, memory_writer):
    """Writing multiple points should append them all."""
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    points = [
        TSPoint("weather", {"temperature": 1.0}, {"device_id": "a"}, ts),
        TSPoint("weather", {"temperature": 2.0}, {"device_id": "b"}, ts),
    ]

    memory_writer.write_points(points)

    assert_that(memory_store.points, contains_exactly(*points))


def test_memory_reader_query_points_by_measurement(memory_writer, memory_reader):
    """Querying should return only points for the requested measurement."""
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    memory_writer.write_point("weather", {"temperature": 1.0}, timestamp=ts)
    memory_writer.write_point("other", {"value": 9.0}, timestamp=ts)

    result = memory_reader.query_points(measurement="weather", start=ts - timedelta(hours=1))

    assert_that(result, contains_exactly(has_properties(measurement="weather")))


def test_memory_reader_query_points_time_bounds(memory_writer, memory_reader):
    """Start is inclusive, stop is exclusive."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    memory_writer.write_point("weather", {"v": 1.0}, timestamp=base)
    memory_writer.write_point("weather", {"v": 2.0}, timestamp=base + timedelta(hours=1))
    memory_writer.write_point("weather", {"v": 3.0}, timestamp=base + timedelta(hours=2))

    result = memory_reader.query_points(
        measurement="weather",
        start=base,
        stop=base + timedelta(hours=2),
    )

    assert_that(result, contains_exactly(
        has_properties(fields={"v": 1.0}),
        has_properties(fields={"v": 2.0}),
    ))


def test_memory_reader_query_points_filters_by_tags(memory_writer, memory_reader):
    """Only points matching every requested tag should be returned."""
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    memory_writer.write_point("weather", {"v": 1.0}, tags={"device_id": "a"}, timestamp=ts)
    memory_writer.write_point("weather", {"v": 2.0}, tags={"device_id": "b"}, timestamp=ts)

    result = memory_reader.query_points(
        measurement="weather",
        start=ts,
        tags={"device_id": "a"},
    )

    assert_that(result, contains_exactly(has_properties(fields={"v": 1.0})))


def test_memory_reader_query_points_projects_fields(memory_writer, memory_reader):
    """When `fields` is given, only those keys should appear in results."""
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    memory_writer.write_point(
        "weather", {"temperature": 20.0, "humidity": 50.0}, timestamp=ts,
    )

    result = memory_reader.query_points(
        measurement="weather", start=ts, fields=["temperature"],
    )

    assert_that(result, contains_exactly(has_properties(fields={"temperature": 20.0})))


def test_memory_reader_query_points_drops_points_without_requested_fields(
    memory_writer, memory_reader,
):
    """Points with none of the requested fields should be dropped."""
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    memory_writer.write_point("weather", {"humidity": 50.0}, timestamp=ts)

    result = memory_reader.query_points(
        measurement="weather", start=ts, fields=["temperature"],
    )

    assert_that(result, empty())


def test_memory_reader_query_points_sorted_by_timestamp(memory_writer, memory_reader):
    """Results should be in ascending timestamp order regardless of insert order."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    memory_writer.write_point("weather", {"v": 2.0}, timestamp=base + timedelta(hours=1))
    memory_writer.write_point("weather", {"v": 1.0}, timestamp=base)

    result = memory_reader.query_points(measurement="weather", start=base)

    assert_that(result, contains_exactly(
        has_properties(fields={"v": 1.0}),
        has_properties(fields={"v": 2.0}),
    ))


def test_memory_reader_latest_returns_most_recent(memory_writer, memory_reader):
    """Latest should return the point with the greatest timestamp in the lookback window."""
    now = datetime.now(UTC)
    memory_writer.write_point("weather", {"v": 1.0}, timestamp=now - timedelta(minutes=10))
    memory_writer.write_point("weather", {"v": 2.0}, timestamp=now - timedelta(minutes=1))

    result = memory_reader.latest("weather", lookback="1h")

    assert_that(result, has_properties(fields={"v": 2.0}))


def test_memory_reader_latest_returns_none_without_data(memory_reader):
    """Latest should return None when no points match."""
    assert_that(memory_reader.latest("weather"), none())


def test_memory_reader_latest_respects_lookback(memory_writer, memory_reader):
    """Points older than the lookback window should not be considered."""
    now = datetime.now(UTC)
    memory_writer.write_point("weather", {"v": 1.0}, timestamp=now - timedelta(days=2))

    assert_that(memory_reader.latest("weather", lookback="1h"), none())


def test_memory_reader_list_tag_values_unique(memory_writer, memory_reader):
    """Duplicate tag values should only be reported once."""
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    memory_writer.write_point("weather", {"v": 1.0}, tags={"device_id": "a"}, timestamp=ts)
    memory_writer.write_point("weather", {"v": 2.0}, tags={"device_id": "a"}, timestamp=ts)
    memory_writer.write_point("weather", {"v": 3.0}, tags={"device_id": "b"}, timestamp=ts)

    result = memory_reader.list_tag_values(measurement="weather", tag_key="device_id")

    assert_that(result, contains_inanyorder("a", "b"))


def test_memory_reader_list_tag_values_contains_filter(memory_writer, memory_reader):
    """The contains filter should narrow results to values containing the substring."""
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    memory_writer.write_point("weather", {"v": 1.0}, tags={"device_id": "sensor-a"}, timestamp=ts)
    memory_writer.write_point("weather", {"v": 2.0}, tags={"device_id": "other-b"}, timestamp=ts)

    result = memory_reader.list_tag_values(
        measurement="weather", tag_key="device_id", contains="sensor",
    )

    assert_that(result, contains_exactly("sensor-a"))


def test_memory_reader_list_tag_values_limit(memory_writer, memory_reader):
    """Limit should cap the number of returned values."""
    ts = datetime(2026, 1, 1, tzinfo=UTC)
    for name in ["a", "b", "c"]:
        memory_writer.write_point("weather", {"v": 1.0}, tags={"device_id": name}, timestamp=ts)

    result = memory_reader.list_tag_values(
        measurement="weather", tag_key="device_id", limit=2,
    )

    assert len(result) == 2
