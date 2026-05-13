"""Unit tests for the api module."""

import asyncio
import json
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from unittest.mock import AsyncMock

from hamcrest import (
    assert_that,
    contains_exactly,
    contains_inanyorder,
    equal_to,
    has_entries,
    has_properties,
)

from tarameteo.api import app, stream_sensor_weather
from tarameteo.ca_client import (
    IssueCertificateRequest,
    IssueCertificateResponse,
    get_ca_client,
)


def make_weather(temperature=20.0, humidity=50.0, pressure=1000.0, **extra):
    return {
        "temperature": temperature,
        "humidity": humidity,
        "pressure": pressure,
        **extra,
    }


def make_aggregate(temperature_min=1.0, temperature_avg=5.0, temperature_max=10.0, **extra):
    return {
        "temperature_min": temperature_min,
        "temperature_avg": temperature_avg,
        "temperature_max": temperature_max,
        **extra,
    }


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


def test_sensors_list(api_app, memory_writer, unique):
    name_a, name_b = unique("text"), unique("text")
    now = datetime.now(UTC)

    memory_writer.write_point(
        "weather", make_weather(), tags={"device_id": name_a}, timestamp=now,
    )
    memory_writer.write_point(
        "weather", make_weather(), tags={"device_id": name_b}, timestamp=now,
    )

    response = api_app.get("/api/sensors")

    assert_that(response.status_code, equal_to(200))
    assert_that(response.json()["sensors"], contains_inanyorder(
        has_entries(name=name_a, kind="timeseries"),
        has_entries(name=name_b, kind="timeseries"),
    ))


def test_sensors_list_includes_aggregate(api_app, memory_writer, unique):
    ts_name, agg_name = unique("text"), unique("text")
    now = datetime.now(UTC)

    memory_writer.write_point(
        "weather", make_weather(), tags={"device_id": ts_name}, timestamp=now,
    )
    memory_writer.write_point(
        "weather_aggregate", make_aggregate(), tags={"device_id": agg_name}, timestamp=now,
    )

    response = api_app.get("/api/sensors")

    assert_that(response.status_code, equal_to(200))
    assert_that(response.json()["sensors"], contains_inanyorder(
        has_entries(name=ts_name, kind="timeseries"),
        has_entries(name=agg_name, kind="aggregate"),
    ))


def test_sensor_get(api_app, memory_writer, unique):
    name = unique("text")
    now = datetime.now(UTC)

    memory_writer.write_point(
        "weather",
        make_weather(temperature=20.0, humidity=50.0, pressure=1000.0, rssi=-70),
        tags={"device_id": name, "latitude": 0.0, "longitude": 0.0},
        timestamp=now - timedelta(hours=1),
    )
    memory_writer.write_point(
        "weather",
        make_weather(temperature=22.0, humidity=60.0, pressure=1020.0, rssi=-74),
        tags={"device_id": name, "latitude": 0.0, "longitude": 0.0},
        timestamp=now - timedelta(minutes=5),
    )

    response = api_app.get(f"/api/sensors/{name}")

    assert_that(response.status_code, equal_to(200))
    assert_that(response.json(), has_entries(
        name=name,
        statistics=has_entries(
            total_readings=2,
            last_24h_readings=2,
            average_temperature=21.0,
            average_humidity=55.0,
            average_pressure=1010.0,
            average_rssi=-72,
        ),
    ))


def test_sensor_get_aggregate_only(api_app, memory_writer, unique):
    name = unique("text")
    now = datetime.now(UTC)

    memory_writer.write_point(
        "weather_aggregate",
        make_aggregate(temperature_min=1.0, temperature_avg=5.0, temperature_max=10.0),
        tags={"device_id": name, "latitude": 46.101244, "longitude": -75.648066},
        timestamp=now - timedelta(minutes=5),
    )

    response = api_app.get(f"/api/sensors/{name}")

    assert_that(response.status_code, equal_to(200))
    assert_that(response.json(), has_entries(
        name=name,
        latitude=46.101244,
        longitude=-75.648066,
        statistics=has_entries(
            total_readings=0,
            last_24h_readings=0,
            average_temperature=None,
            average_humidity=None,
            average_pressure=None,
            average_rssi=None,
        ),
    ))


def test_sensor_get_aggregate_only_missing_location(api_app, memory_writer, unique):
    name = unique("text")
    now = datetime.now(UTC)

    memory_writer.write_point(
        "weather_aggregate",
        make_aggregate(temperature_min=1.0, temperature_avg=5.0, temperature_max=10.0),
        tags={"device_id": name},
        timestamp=now - timedelta(minutes=5),
    )

    response = api_app.get(f"/api/sensors/{name}")

    assert_that(response.status_code, equal_to(404))


def test_sensor_get_missing(api_app, unique):
    response = api_app.get(f"/api/sensors/{unique('text')}")

    assert_that(response.status_code, equal_to(404))


def test_sensor_weather_latest(api_app, memory_writer, unique):
    name = unique("text")
    now = datetime.now(UTC)

    memory_writer.write_point(
        "weather",
        make_weather(temperature=19.0),
        tags={"device_id": name, "latitude": 0.0, "longitude": 0.0},
        timestamp=now - timedelta(minutes=10),
    )
    memory_writer.write_point(
        "weather",
        make_weather(temperature=23.5),
        tags={"device_id": name, "latitude": 0.0, "longitude": 0.0},
        timestamp=now - timedelta(minutes=1),
    )

    response = api_app.get(f"/api/sensors/{name}/weather/latest")

    assert_that(response.status_code, equal_to(200))
    assert_that(response.json(), has_entries(
        sensor=name,
        temperature=23.5,
    ))


def test_sensor_weather_latest_missing(api_app, unique):
    name = unique("text")

    response = api_app.get(f"/api/sensors/{name}/weather/latest")

    assert_that(response.status_code, equal_to(404))


def test_sensor_weather_range(api_app, memory_writer, unique):
    name = unique("text")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 2, tzinfo=UTC)

    memory_writer.write_point(
        "weather", make_weather(temperature=1.0),
        tags={"device_id": name, "latitude": 0.0, "longitude": 0.0},
        timestamp=start + timedelta(hours=1),
    )
    memory_writer.write_point(
        "weather", make_weather(temperature=2.0),
        tags={"device_id": name, "latitude": 0.0, "longitude": 0.0},
        timestamp=end + timedelta(hours=1),
    )

    response = api_app.get(
        f"/api/sensors/{name}/weather",
        params={"start": start.isoformat(), "end": end.isoformat(), "limit": 500},
    )

    assert_that(response.status_code, equal_to(200))
    assert_that(response.json(), contains_exactly(
        has_entries(sensor=name, temperature=1.0),
    ))


def test_sensor_weather_aggregate(api_app, memory_writer, unique):
    name = unique("text")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 3, tzinfo=UTC)

    memory_writer.write_point(
        "weather_aggregate", make_aggregate(temperature_min=1.0, temperature_avg=5.0, temperature_max=10.0),
        tags={"device_id": name}, timestamp=start + timedelta(hours=12),
    )
    memory_writer.write_point(
        "weather_aggregate", make_aggregate(temperature_min=2.0, temperature_avg=6.0, temperature_max=11.0),
        tags={"device_id": name}, timestamp=end + timedelta(hours=12),
    )

    response = api_app.get(
        f"/api/sensors/{name}/weather/aggregate",
        params={"start": start.isoformat(), "end": end.isoformat()},
    )

    assert_that(response.status_code, equal_to(200))
    assert_that(response.json(), contains_exactly(
        has_entries(sensor=name, temperature_min=1.0, temperature_avg=5.0, temperature_max=10.0),
    ))


async def test_stream_sensor_weather(memory_queue, unique):
    name = unique("text")
    payload = json.dumps({
        "sensor": name,
        "timestamp": datetime.now(UTC).isoformat(),
        "temperature": 22.5,
        "humidity": 60.0,
        "pressure": 1013.25,
        "altitude": None,
        "rssi": None,
        "retry_count": None,
    })

    # is_disconnected returns False once (allow one event through) then True
    mock_request = AsyncMock()
    mock_request.is_disconnected.side_effect = [False, True]

    response = await stream_sensor_weather(name=name, request=mock_request, queue=memory_queue)

    async def publish_after_subscribe():
        # Yield to let the SSE generator subscribe and begin awaiting a message.
        await asyncio.sleep(0)
        await memory_queue.publish(f"weather:{name}", payload)

    task = asyncio.create_task(publish_after_subscribe())
    events = [chunk async for chunk in response.body_iterator]
    await task

    assert_that(events, contains_exactly(f"data: {payload}\n\n"))
