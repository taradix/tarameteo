"""Integration tests for the fixtures module."""

from pathlib import Path

from hamcrest import (
    all_of,
    assert_that,
    contains_string,
)


def test_make_certs(make_certs):
    """Making certs should return the path to a cafile, certfile, and keyfile."""
    certs = make_certs("client-id")
    assert_that(Path(certs['cafile']).read_text(), all_of(
        contains_string("-----BEGIN CERTIFICATE-----"),
        contains_string("-----END CERTIFICATE-----"),
    ))
    assert_that(Path(certs['certfile']).read_text(), all_of(
        contains_string("-----BEGIN CERTIFICATE-----"),
        contains_string("-----END CERTIFICATE-----"),
    ))
    assert_that(Path(certs['keyfile']).read_text(), all_of(
        contains_string("-----BEGIN EC PRIVATE KEY-----"),
        contains_string("-----END EC PRIVATE KEY-----"),
    ))
