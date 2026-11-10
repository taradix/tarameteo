"""Unit tests for the api module."""

import asyncio
import json
import re
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from unittest.mock import AsyncMock

import pytest
from hamcrest import (
    all_of,
    assert_that,
    close_to,
    contains_exactly,
    contains_inanyorder,
    contains_string,
    equal_to,
    has_entries,
    has_properties,
    is_not,
    none,
    not_none,
    only_contains,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tarameteo.alerts import Alert, AlertStore
from tarameteo.api import app, get_alert_store, stream_sensor_weather
from tarameteo.ca_client import (
    IssueCertificateRequest,
    IssueCertificateResponse,
    get_ca_client,
)
from tarameteo.models import SQLModel
from tarameteo.tokens import sign_token


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


def located(name, latitude="45.5", longitude="-73.6"):
    return {"device_id": name, "latitude": latitude, "longitude": longitude}


def test_sensors_list(api_app, memory_writer, unique):
    name_a, name_b = unique("text"), unique("text")
    now = datetime.now(UTC)

    memory_writer.write_point(
        "weather", make_weather(), tags=located(name_a), timestamp=now,
    )
    memory_writer.write_point(
        "weather", make_weather(), tags=located(name_b), timestamp=now,
    )

    response = api_app.get("/api/sensors")

    assert_that(response.status_code, equal_to(200))
    assert_that(response.json()["sensors"], contains_inanyorder(
        has_entries(name=name_a, kind="timeseries", latitude=45.5, longitude=-73.6, distance_km=None),
        has_entries(name=name_b, kind="timeseries", latitude=45.5, longitude=-73.6, distance_km=None),
    ))


def test_sensors_list_includes_aggregate(api_app, memory_writer, unique):
    ts_name, agg_name = unique("text"), unique("text")
    now = datetime.now(UTC)

    memory_writer.write_point(
        "weather", make_weather(), tags=located(ts_name), timestamp=now,
    )
    memory_writer.write_point(
        "weather_aggregate", make_aggregate(), tags=located(agg_name), timestamp=now,
    )

    response = api_app.get("/api/sensors")

    assert_that(response.status_code, equal_to(200))
    assert_that(response.json()["sensors"], contains_inanyorder(
        has_entries(name=ts_name, kind="timeseries"),
        has_entries(name=agg_name, kind="aggregate"),
    ))


def test_sensors_list_uses_latest_location(api_app, memory_writer, unique):
    name = unique("text")
    now = datetime.now(UTC)

    memory_writer.write_point(
        "weather", make_weather(), tags=located(name, "45.0", "-73.0"), timestamp=now - timedelta(hours=1),
    )
    memory_writer.write_point(
        "weather", make_weather(), tags=located(name, "46.0", "-74.0"), timestamp=now,
    )

    response = api_app.get("/api/sensors")

    assert_that(response.json()["sensors"], contains_exactly(
        has_entries(name=name, latitude=46.0, longitude=-74.0),
    ))


def test_sensors_list_skips_sensor_without_location(api_app, memory_writer, unique):
    name = unique("text")
    memory_writer.write_point(
        "weather", make_weather(), tags={"device_id": name}, timestamp=datetime.now(UTC),
    )

    response = api_app.get("/api/sensors")

    assert_that(response.json()["sensors"], equal_to([]))


def test_sensors_list_near_sorts_by_distance_within_radius(api_app, memory_writer, unique):
    montreal, quebec, toronto = unique("text"), unique("text"), unique("text")
    now = datetime.now(UTC)
    memory_writer.write_point("weather", make_weather(), tags=located(quebec, "46.81", "-71.21"), timestamp=now)
    memory_writer.write_point("weather", make_weather(), tags=located(toronto, "43.65", "-79.38"), timestamp=now)
    memory_writer.write_point(
        "weather_aggregate", make_aggregate(), tags=located(montreal, "45.50", "-73.57"), timestamp=now,
    )

    response = api_app.get("/api/sensors", params={"latitude": 45.5, "longitude": -73.6, "radius": 300})

    assert_that(response.status_code, equal_to(200))
    assert_that(response.json()["sensors"], contains_exactly(
        has_entries(name=montreal, kind="aggregate", distance_km=close_to(2.3, 0.1)),
        has_entries(name=quebec, kind="timeseries", distance_km=close_to(235, 2)),
    ))


@pytest.fixture
def cities(memory_writer):
    """Montreal and Quebec weather sensors, and an aggregate across the antimeridian in Fiji."""
    now = datetime.now(UTC)
    memory_writer.write_point("weather", make_weather(), tags=located("Montreal", "45.50", "-73.57"), timestamp=now)
    memory_writer.write_point("weather", make_weather(), tags=located("Quebec", "46.81", "-71.21"), timestamp=now)
    memory_writer.write_point(
        "weather_aggregate", make_aggregate(), tags=located("Fiji", "-17.80", "179.50"), timestamp=now,
    )


@pytest.mark.parametrize("params, names", [
    ({"names": ["Quebec", "Fiji", "Nowhere"]}, ["Fiji", "Quebec"]),
    ({"q": "MONT"}, ["Montreal"]),
    ({"bbox": "-75,45,-72,46"}, ["Montreal"]),
    ({"bbox": "179,-20,-179,-15"}, ["Fiji"]),
    ({"q": "e", "latitude": 46.8, "longitude": -71.2}, ["Quebec", "Montreal"]),
])
def test_sensors_list_filters(api_app, cities, params, names):
    response = api_app.get("/api/sensors", params=params)

    assert_that(response.status_code, equal_to(200))
    assert_that(response.json(), has_entries(
        sensors=contains_exactly(*(has_entries(name=n) for n in names)),
        truncated=False,
    ))


def test_sensors_list_limit_truncates_in_name_order(api_app, cities):
    response = api_app.get("/api/sensors", params={"limit": 2})

    assert_that(response.json(), has_entries(
        sensors=contains_exactly(has_entries(name="Fiji"), has_entries(name="Montreal")),
        truncated=True,
    ))


def test_sensor_clusters_group_by_zoom(api_app, cities):
    canada = {"bbox": "-80,40,-70,50"}

    far = api_app.get("/api/sensors/clusters", params={**canada, "zoom": 3})
    near = api_app.get("/api/sensors/clusters", params={**canada, "zoom": 8})

    # At zoom 3 a cell spans 11.25°, which holds both cities; at zoom 8 it spans 0.35°.
    assert_that(far.json()["clusters"], contains_exactly(
        has_entries(count=2, latitude=close_to(46.155, 0.001), longitude=close_to(-72.39, 0.001), sensor=None),
    ))
    assert_that(near.json()["clusters"], contains_inanyorder(
        has_entries(count=1, latitude=45.5, sensor=has_entries(name="Montreal", kind="timeseries")),
        has_entries(count=1, latitude=46.81, sensor=has_entries(name="Quebec")),
    ))


@pytest.mark.parametrize("path, params", [
    ("/api/sensors", {"bbox": "1,2,3"}),
    ("/api/sensors", {"bbox": "a,b,c,d"}),
    ("/api/sensors", {"bbox": "-181,0,0,1"}),
    ("/api/sensors", {"bbox": "0,10,1,5"}),
    ("/api/sensors", {"bbox": "nan,0,1,1"}),
    ("/api/sensors", {"q": ""}),
    ("/api/sensors", {"names": [str(i) for i in range(101)]}),
    ("/api/sensors", {"limit": 0}),
    ("/api/sensors", {"limit": 201}),
    ("/api/sensors/clusters", {"bbox": "0,0,1,1"}),
    ("/api/sensors/clusters", {"zoom": 4}),
    ("/api/sensors/clusters", {"bbox": "0,0,1,1", "zoom": 23}),
])
def test_sensors_list_rejects_invalid_filters(api_app, path, params):
    response = api_app.get(path, params=params)

    assert_that(response.status_code, equal_to(422))


@pytest.mark.parametrize("params", [
    {"latitude": 45.5},
    {"longitude": -73.6},
    {"radius": 50},
    {"latitude": 91, "longitude": 0},
    {"latitude": 0, "longitude": 181},
    {"latitude": 0, "longitude": 0, "radius": 0},
])
def test_sensors_list_rejects_invalid_point(api_app, params):
    response = api_app.get("/api/sensors", params=params)

    assert_that(response.status_code, equal_to(422))


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


@pytest.fixture
def alert_api(api_app):
    """api_app with alerts configured: an in-memory store, and a notifier mock to read emails from."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    db = Session(engine)
    store = AlertStore(db)
    app.dependency_overrides[get_alert_store] = lambda: store
    state = api_app.app.state
    state.alert_secret, state.alert_base_url, state.notifier = "s", "http://test", AsyncMock()
    try:
        yield api_app, store, state.notifier
    finally:
        app.dependency_overrides.pop(get_alert_store, None)
        db.close()
        engine.dispose()


NEW_ALERT = {"email": "user@example.com", "sensor": "outdoor", "field": "temperature", "condition": "below", "threshold": -20}


def _link(notifier) -> str:
    """The path of the link in the last email."""
    body = notifier.send.call_args.args[2]
    return re.search(r"http://test(\S+)", body).group(1)


def test_alert_confirm_needs_a_button_press(alert_api):
    client, store, notifier = alert_api

    assert_that(client.post("/api/alerts", json={**NEW_ALERT, "language": "fr"}).status_code, equal_to(201))
    link = _link(notifier)
    assert_that(notifier.send.call_args.args[1], equal_to("Confirmez votre alerte météo"))

    # Opening the link, as a link scanner would, changes nothing.
    page = client.get(link)
    assert_that(page.text, all_of(contains_string('<form method="post">'), contains_string("en dessous de -20 °C")))
    assert_that(store.count_by_email("user@example.com", confirmed=True), equal_to(0))

    assert_that(client.post(link).text, contains_string("Alerte confirmée"))
    assert_that(store.count_by_email("user@example.com", confirmed=True), equal_to(1))
    assert_that(client.get(link).text, is_not(contains_string("<form")))


def test_alert_unsubscribe_needs_a_post(alert_api):
    client, store, _ = alert_api
    store.create(Alert(id="a1", confirmed=True, **NEW_ALERT))
    link = "/api/alerts/unsubscribe/" + sign_token({"alert_id": "a1", "action": "unsubscribe"}, "s")

    assert_that(client.get(link).text, contains_string("Stop this alert?"))
    assert_that(store.get("a1"), not_none())

    # The one-click unsubscribe POST from a mail client.
    response = client.post(link, data={"List-Unsubscribe": "One-Click"})
    assert_that(response.status_code, equal_to(200))
    assert_that(store.get("a1"), none())
    assert_that(client.post(link).status_code, equal_to(404))


@pytest.mark.parametrize("path", [
    "/api/alerts/confirm/bad.token",
    "/api/alerts/unsubscribe/" + sign_token({"alert_id": "a1", "action": "confirm"}, "s"),
    "/api/alerts/confirm/" + sign_token({"alert_id": "a1", "action": "confirm"}, "s", expires_in=-1),
    "/api/alerts/confirm/" + sign_token({"alert_id": "a1", "action": "confirm"}, "other"),
])
def test_alert_links_reject_bad_tokens(alert_api, path):
    client, _, _ = alert_api

    assert_that(client.get(path).status_code, equal_to(400))
    assert_that(client.post(path).status_code, equal_to(400))


def test_alert_create_limits_pending_confirmations_silently(alert_api):
    client, _, notifier = alert_api

    responses = [client.post("/api/alerts", json=NEW_ALERT) for _ in range(5)]

    assert_that([r.json() for r in responses], only_contains(has_entries(status="confirmation_sent")))
    assert_that(notifier.send.call_count, equal_to(3))


def test_alert_create_caps_alerts_per_email(alert_api):
    client, store, _ = alert_api
    for i in range(20):
        store.create(Alert(id=f"a{i}", confirmed=True, **NEW_ALERT))

    assert_that(client.post("/api/alerts", json=NEW_ALERT).status_code, equal_to(409))
