"""Unit tests for the auth module."""

import pytest
from fastapi import HTTPException
from hamcrest import assert_that, has_properties

from tarameteo.auth import bearer_token


def test_require_valid_token(unique):
    """Requiring a valid token should not raise."""
    token = unique("text")
    bearer_token("CA_TOKEN")(f"Bearer {token}", {"CA_TOKEN": token})


def test_require_missing_token():
    """Requiring a missing token should raise a 401 exception."""
    with pytest.raises(HTTPException) as e:
        bearer_token("CA_TOKEN")(None, {"CA_TOKEN": "b"})

    assert_that(e.value, has_properties(status_code=401))


def test_require_invalid_token():
    """Requiring a missing token should raise a 403 exception."""
    with pytest.raises(HTTPException) as e:
        bearer_token("CA_TOKEN")("Bearer a", {"CA_TOKEN": "b"})

    assert_that(e.value, has_properties(status_code=403))


def test_require_unconfigured_token():
    """Requiring a token when the variable is unset should raise a 503 exception, not let everyone in."""
    with pytest.raises(HTTPException) as e:
        bearer_token("CA_TOKEN")("Bearer ", {"CA_TOKEN": ""})

    assert_that(e.value, has_properties(status_code=503))
