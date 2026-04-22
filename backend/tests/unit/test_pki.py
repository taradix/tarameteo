"""Unit tests for the pki module."""

import pytest
from cryptography import x509
from hamcrest import (
    all_of,
    assert_that,
    contains_string,
    has_properties,
)

from tarameteo.crypto import (
    generate_key_pem,
    load_cert,
)
from tarameteo.pki import (
    create_csr_pem,
    self_sign_ca_key_pem,
    sign_csr_pem,
)


def test_create_csr_pem(unique):
    """Creating a CSR should have BEGIN and END delimiters."""
    common_name = unique("text")
    key_pem = generate_key_pem()
    csr_pem = create_csr_pem(key_pem, common_name)
    assert_that(csr_pem, all_of(
        contains_string("-----BEGIN CERTIFICATE REQUEST-----"),
        contains_string("-----END CERTIFICATE REQUEST-----"),
    ))


def test_sign_csr_pem(unique):
    """Signing a CSR should return a certificate with BEGIN and END delimiters."""
    subject, common_name = unique("subject"), unique("text")
    ca_key_pem = generate_key_pem()
    ca_cert_material = self_sign_ca_key_pem(ca_key_pem, subject=subject)
    key_pem = generate_key_pem()
    csr_pem = create_csr_pem(key_pem, common_name)
    cert_material = sign_csr_pem(csr_pem, ca_key_pem=ca_key_pem, ca_cert_pem=ca_cert_material.cert_pem)
    assert_that(cert_material, has_properties(
        cert_pem=all_of(
            contains_string("-----BEGIN CERTIFICATE-----"),
            contains_string("-----END CERTIFICATE-----"),
        ),
        chain_pem=[ca_cert_material.cert_pem],
    ))


def test_sign_csr_pem_copies_san_from_csr(unique):
    """SAN DNS entries in the CSR should appear in the signed certificate."""
    subject, common_name, san = unique("subject"), unique("text"), unique("text")
    ca_key_pem = generate_key_pem()
    ca_cert_material = self_sign_ca_key_pem(ca_key_pem, subject=subject)
    key_pem = generate_key_pem()
    csr_pem = create_csr_pem(key_pem, common_name, san_dns=[san])
    cert_material = sign_csr_pem(
        csr_pem,
        ca_key_pem=ca_key_pem,
        ca_cert_pem=ca_cert_material.cert_pem,
        server_auth=True,
    )
    cert = load_cert(cert_material.cert_pem)
    ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    assert_that(ext.value.get_values_for_type(x509.DNSName), [san])


def test_sign_csr_pem_server_auth_requires_san(unique):
    """Server-auth certificates must carry at least one SAN."""
    subject, common_name = unique("subject"), unique("text")
    ca_key_pem = generate_key_pem()
    ca_cert_material = self_sign_ca_key_pem(ca_key_pem, subject=subject)
    key_pem = generate_key_pem()
    csr_pem = create_csr_pem(key_pem, common_name)
    with pytest.raises(ValueError, match="at least one SAN"):
        sign_csr_pem(
            csr_pem,
            ca_key_pem=ca_key_pem,
            ca_cert_pem=ca_cert_material.cert_pem,
            server_auth=True,
        )


def test_self_sign_ca_key_pem(unique):
    """Self-signing a CA key should return a certificate with BEGIN and END delimiters."""
    subject = unique("subject")
    ca_key_pem = generate_key_pem()
    cert_material = self_sign_ca_key_pem(ca_key_pem, subject=subject)
    assert_that(cert_material, has_properties(
        cert_pem=all_of(
            contains_string("-----BEGIN CERTIFICATE-----"),
            contains_string("-----END CERTIFICATE-----"),
        ),
        chain_pem=[],
    ))
