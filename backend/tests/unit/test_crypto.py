"""Unit tests for the crypto module."""

import pytest
from hamcrest import (
    all_of,
    assert_that,
    contains_string,
)

from tarameteo.crypto import (
    KeyAlgorithm,
    KeySpec,
    generate_key_pem,
    key_matches_cert,
)
from tarameteo.pki import self_sign_ca_key_pem


def test_key_matches_cert(unique):
    """A certificate generated from a key should match."""
    subject = unique("subject")
    key_pem = generate_key_pem()
    cert_material = self_sign_ca_key_pem(key_pem, subject=subject)
    assert key_matches_cert(key_pem, cert_material.cert_pem)


@pytest.mark.parametrize("key_algorithm", [
    KeyAlgorithm.EC,
    KeyAlgorithm.RSA,
])
def test_generate_key_pem(key_algorithm):
    """Generating a key should have BEGIN and END delimiters."""
    key_spec = KeySpec(algorithm=key_algorithm)
    key_pem = generate_key_pem(key_spec)
    assert_that(key_pem, all_of(
        contains_string(f"-----BEGIN {key_algorithm.name} PRIVATE KEY-----"),
        contains_string(f"-----END {key_algorithm.name} PRIVATE KEY-----"),
    ))
