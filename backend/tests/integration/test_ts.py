"""Integration tests for the ts module."""

from tarameteo.ts import TSPoint


def test_influx_writer(influxdb_reader, influxdb_writer, unique):
    measurement = unique("text")
    point = TSPoint(measurement, {"test": 1})
    influxdb_writer.write_points([point])
    result = influxdb_reader.latest(measurement)
    assert result == point

