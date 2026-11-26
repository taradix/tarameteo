"""Integration tests for the nginx service."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_nginx_redirects_http_to_https(nginx_service):
    async with AsyncClient(base_url=f"http://{nginx_service.ip}") as client:
        response = await client.get("/api/sensors")

    assert response.status_code == 301
    assert response.headers["location"] == f"https://{nginx_service.ip}/api/sensors"


@pytest.mark.asyncio
async def test_nginx_proxies_api(nginx_client):
    response = await nginx_client.get("/api/sensors")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_nginx_proxies_frontend(nginx_client):
    response = await nginx_client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
