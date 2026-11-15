"""Unit tests for the InfluxWriter and InfluxReader against fake Influx APIs."""

from attrs import define, field
from hamcrest import (
    assert_that,
    calling,
    has_length,
    none,
    raises,
)
from influxdb_client.rest import ApiException
from urllib3.exceptions import NewConnectionError

from tarameteo.ts import InfluxReader, InfluxWriter


@define
class FakeApi:
    """Fails with each error in turn, then succeeds and records the call."""

    errors: list[Exception] = field(factory=list)
    calls: list[dict] = field(factory=list)

    def write(self, **kwargs):
        if self.errors:
            raise self.errors.pop(0)
        self.calls.append(kwargs)

    def query(self, **kwargs):
        self.write(**kwargs)
        return []


def writer(api):
    return InfluxWriter(write_api=api, org="org", bucket="bucket", retry_backoff_seconds=0)


def test_influx_writer_write_point_without_tags():
    """A point without tags should be written, not crash on the missing tags."""
    api = FakeApi()

    writer(api).write_point("weather", {"temperature": 20.0})

    assert_that(api.calls, has_length(1))


def test_influx_writer_retries_transient_errors():
    """Influx being down or overloaded should be retried until it answers."""
    api = FakeApi(errors=[ApiException(status=503), NewConnectionError(None, "refused")])

    writer(api).write_point("weather", {"temperature": 20.0})

    assert_that(api.calls, has_length(1))


def test_influx_writer_does_not_retry_rejected_requests():
    """A bad token or request should fail at once instead of being retried."""
    api = FakeApi(errors=[ApiException(status=401), ApiException(status=503)])

    assert_that(calling(writer(api).write_point).with_args("weather", {"temperature": 20.0}), raises(ApiException))
    # The 503 behind the 401 was never reached.
    assert_that(api.errors, has_length(1))


def test_influx_writer_gives_up_after_max_retries():
    """A persistent outage should raise after the last retry."""
    api = FakeApi(errors=[ApiException(status=503)] * 5)

    assert_that(calling(writer(api).write_point).with_args("weather", {"temperature": 20.0}), raises(ApiException))
    assert_that(api.errors, has_length(1))


def test_influx_reader_retries_transient_errors():
    """Queries should be retried the same way as writes."""
    api = FakeApi(errors=[ApiException(status=429)])
    reader = InfluxReader(query_api=api, org="org", bucket="bucket", retry_backoff_seconds=0)

    assert_that(reader.latest("weather"), none())
    assert_that(api.calls, has_length(1))
