"""Integration tests for the ca_client module."""

from datetime import (
    UTC,
    datetime,
)

from hamcrest import (
    assert_that,
    contains,
    contains_string,
    greater_than,
    has_properties,
    less_than,
)

from tarameteo.ca_client import IssueCertificateRequest
from tarameteo.crypto import generate_key_pem
from tarameteo.pki import create_csr_pem


def test_ca_client_issue_certificate(ca_client, unique):
    device_id = unique("text")
    key_pem = generate_key_pem()
    csr_pem = create_csr_pem(key_pem, device_id)

    request = IssueCertificateRequest(csr_pem=csr_pem)
    response = ca_client.issue_certificate(request)
    assert_that(response, has_properties(
        cert_pem=contains_string("-----BEGIN CERTIFICATE-----"),
        chain_pem=contains(contains_string("-----BEGIN CERTIFICATE-----")),
        not_before=less_than(datetime.now(UTC)),
        not_after=greater_than(datetime.now(UTC)),
    ))
