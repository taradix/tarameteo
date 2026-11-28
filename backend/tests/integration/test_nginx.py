"""Integration tests for the nginx service."""

import pytest
from hamcrest import assert_that, contains_string, has_entries, has_properties
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_nginx_redirects_http_to_https(nginx_service):
    async with AsyncClient(base_url=f"http://{nginx_service.ip}") as client:
        response = await client.get("/api/sensors")

    assert_that(response, has_properties(
        status_code=301,
        headers=has_entries(location=f"https://{nginx_service.ip}/api/sensors"),
    ))


@pytest.mark.asyncio
async def test_nginx_proxies_api(nginx_client):
    response = await nginx_client.get("/api/sensors")

    assert_that(response, has_properties(
        status_code=200,
        headers=has_entries({"content-type": "application/json"}),
    ))


@pytest.mark.asyncio
async def test_nginx_proxies_frontend(nginx_client):
    response = await nginx_client.get("/")

    assert_that(response, has_properties(
        status_code=200,
        headers=has_entries({"content-type": contains_string("text/html")}),
    ))
