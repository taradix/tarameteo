"""Unit tests for the api module."""

from datetime import (
    UTC,
    datetime,
    timedelta,
)

from hamcrest import (
    assert_that,
    has_entries,
    has_properties,
)

from tarameteo.api import app
from tarameteo.ca_client import (
    IssueCertificateRequest,
    IssueCertificateResponse,
    get_ca_client,
)


def test_healthz_get(api_app):
    """Getting the /healthz should return an "ok" status."""
    result = api_app.get("/healthz")

    assert_that(result.json(), has_entries(status="ok"))


def test_certs_post(api_app, unique):
    csr_pem, cert_pem, ca_pem = unique("text"), unique("text"), unique("text")
    serial_number, subject, issuer = unique("integer"), unique("text"), unique("text")
    now = datetime.now(UTC)
    not_before = now - timedelta(hours=2)
    not_after = now + timedelta(days=30)

    class StubCAClient:
        def issue_certificate(self, request: IssueCertificateRequest) -> IssueCertificateResponse:
            assert_that(request, has_properties(csr_pem=csr_pem))
            return IssueCertificateResponse(
                cert_pem=cert_pem,
                chain_pem=[ca_pem],
                serial_number=serial_number,
                not_before=not_before,
                not_after=not_after,
                subject=subject,
                issuer=issuer,
            )

    app.dependency_overrides[get_ca_client] = lambda: StubCAClient()

    response = api_app.post("/api/certs", json={
        "csr_pem": csr_pem,
    })
    assert_that(response.json(), has_entries(
        cert_pem=cert_pem,
        chain_pem=[ca_pem],
        serial_number=serial_number,
        subject=subject,
        issuer=issuer,
    ))
