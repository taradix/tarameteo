"""Unit tests for the ca module."""

from hamcrest import (
    assert_that,
    has_entries,
)


def test_healthz_get(ca_app):
    """Getting the /healthz should return an "ok" status."""
    result = ca_app.get("/healthz")

    assert_that(result.json(), has_entries(status="ok"))
