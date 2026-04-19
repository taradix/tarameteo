"""Integration tests for the api module."""

import pytest
from hamcrest import (
    assert_that,
    contains,
    contains_string,
    has_entries,
)

from tarameteo.crypto import generate_key_pem
from tarameteo.pki import create_csr_pem


@pytest.mark.asyncio
async def test_api_certs_post(api_client, unique):
    device_id = unique("text")
    key_pem = generate_key_pem()
    csr_pem = create_csr_pem(key_pem, device_id)
    response = await api_client.post("/api/certs", json={
        "csr_pem": csr_pem,
    })
    assert_that(response.json(), has_entries(
        cert_pem=contains_string("-----BEGIN CERTIFICATE-----"),
        chain_pem=contains(contains_string("-----BEGIN CERTIFICATE-----")),
    ))
