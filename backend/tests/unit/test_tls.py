"""Unit tests for the tls module."""

import pytest
from hamcrest import (
    assert_that,
    has_properties,
    not_none,
)

from tarameteo.crypto import generate_key_pem
from tarameteo.pki import self_sign_ca_key_pem
from tarameteo.tls import TLSCredentials


@pytest.fixture
def tls_credentials(tmp_path):
    return TLSCredentials(
        key_path=tmp_path / "test.key",
        cert_path=tmp_path / "test.pem",
        ca_path=tmp_path / "ca.crt",
    )


def test_tls_credentals_from_device_id(tls_credentials):
    """Instantiating TLS credentials from device ID should set all paths."""
    assert_that(tls_credentials, has_properties(
        key_path=not_none(),
        cert_path=not_none(),
        ca_path=not_none(),
    ))


def test_tls_credentials_exists_with_ca(tls_credentials):
    """Checking for existence with CA should check the CA path."""
    assert tls_credentials.exists() is False
    tls_credentials.save("", cert_pem="", ca_pem="")
    assert tls_credentials.exists() is True


def test_tls_credentials_exists_without_ca(tmp_path):
    """Checking for existence without CA should not check the CA path."""
    tls_credentials = TLSCredentials(
        key_path=tmp_path / "test.key",
        cert_path=tmp_path / "test.pem",
    )
    assert tls_credentials.exists() is False
    tls_credentials.save("", cert_pem="")
    assert tls_credentials.exists() is True


def test_tls_credentials_key_matches_cert(tls_credentials):
    """Checking when a private key corresponds to the cert's public key."""
    key_pem = generate_key_pem()
    cert_pem = self_sign_ca_key_pem(key_pem, subject="/CN=test").cert_pem

    tls_credentials.save(key_pem, cert_pem)

    assert tls_credentials.key_matches_cert() is True


def test_tls_credentials_key_doesnt_match_cert(tls_credentials):
    """Checking when a private key doesn't correspond to the cert's public key."""
    key_pem = generate_key_pem()
    cert_pem = self_sign_ca_key_pem(key_pem, subject="/CN=test").cert_pem
    other_pem = generate_key_pem()

    tls_credentials.save(other_pem, cert_pem)

    assert tls_credentials.key_matches_cert() is False
