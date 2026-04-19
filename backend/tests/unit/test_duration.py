"""Unit tests for the duration module."""

from datetime import timedelta

import pytest

from tarameteo.duration import parse_duration


@pytest.mark.parametrize("duration, expected", [
    ("1d", timedelta(days=1)),
    ("1h", timedelta(hours=1)),
    ("1m", timedelta(minutes=1)),
    ("1s", timedelta(seconds=1)),
])
def test_parse_duration(duration, expected):
    """A duration should include days, hours, minutes, or seconds."""
    result = parse_duration(duration)
    assert result == expected
