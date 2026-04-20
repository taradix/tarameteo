"""Integration tests for the api module."""

from datetime import (
    UTC,
    datetime,
    timedelta,
)

import pytest
from hamcrest import (
    assert_that,
    contains,
    contains_string,
    greater_than_or_equal_to,
    has_entries,
    has_item,
)

from tarameteo.crypto import generate_key_pem
from tarameteo.pki import create_csr_pem
from tarameteo.ts import TSPoint


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


@pytest.fixture
def weather_points(influxdb_writer, unique):
    """Write a deterministic series of weather points for a fresh sensor."""
    sensor = unique("text")
    now = datetime.now(UTC).replace(microsecond=0)
    points = [
        TSPoint(
            measurement="weather",
            fields={
                "temperature": 20.0 + i,
                "humidity": 50.0 + i,
                "pressure": 1000.0 + i,
                "rssi": -70 - i,
                "retry_count": i,
            },
            tags={"device_id": sensor},
            timestamp=now - timedelta(minutes=(5 - i)),
        )
        for i in range(5)
    ]
    influxdb_writer.write_points(points)
    return sensor, points


@pytest.mark.asyncio
async def test_api_sensors_list(api_client, weather_points):
    sensor, _ = weather_points
    response = await api_client.get("/api/sensors")
    assert_that(response.json(), has_entries(sensors=has_item(sensor)))


@pytest.mark.asyncio
async def test_api_sensor_get(api_client, weather_points):
    sensor, points = weather_points
    response = await api_client.get(f"/api/sensors/{sensor}")
    body = response.json()
    assert_that(body, has_entries(
        name=sensor,
        statistics=has_entries(
            total_readings=greater_than_or_equal_to(len(points)),
            last_24h_readings=greater_than_or_equal_to(len(points)),
        ),
    ))


@pytest.mark.asyncio
async def test_api_sensor_weather_latest(api_client, weather_points):
    sensor, points = weather_points
    expected = points[-1]
    response = await api_client.get(f"/api/sensors/{sensor}/weather/latest")
    assert_that(response.json(), has_entries(
        sensor=sensor,
        temperature=expected.fields["temperature"],
        humidity=expected.fields["humidity"],
        pressure=expected.fields["pressure"],
    ))


@pytest.mark.asyncio
async def test_api_sensor_weather_range(api_client, weather_points):
    sensor, points = weather_points
    start = (points[0].timestamp - timedelta(minutes=1)).isoformat()
    end = (points[-1].timestamp + timedelta(minutes=1)).isoformat()
    response = await api_client.get(
        f"/api/sensors/{sensor}/weather",
        params={"start": start, "end": end},
    )
    body = response.json()
    assert len(body) == len(points)
    assert_that(body[0], has_entries(sensor=sensor))
