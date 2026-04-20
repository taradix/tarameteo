"""Unit tests for the ca module."""

import pytest
from fastapi import HTTPException
from hamcrest import (
    assert_that,
    has_entries,
    has_properties,
)

from tarameteo.ca import require_token


def test_require_valid_token(unique):
    """Requiring a valid token should not raise."""
    token = unique("text")
    require_token(f"Bearer {token}", {"CA_TOKEN": token})


def test_require_missing_token():
    """Requiring a missing token should raise a 401 exception."""
    with pytest.raises(HTTPException) as e:
        require_token(None, {"CA_TOKEN": "b"})

    assert_that(e.value, has_properties(status_code=401))


def test_require_invalid_token():
    """Requiring a missing token should raise a 403 exception."""
    with pytest.raises(HTTPException) as e:
        require_token("Bearer a", {"CA_TOKEN": "b"})

    assert_that(e.value, has_properties(status_code=403))


def test_healthz_get(ca_app):
    """Getting the /healthz should return an "ok" status."""
    result = ca_app.get("/healthz")

    assert_that(result.json(), has_entries(status="ok"))
