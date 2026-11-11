"""Tests for tarameteo.alert_checker."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from hamcrest import (
    all_of,
    assert_that,
    contains_exactly,
    contains_string,
    equal_to,
    has_entries,
    starts_with,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tarameteo.alert_checker import check_alerts
from tarameteo.alerts import Alert, AlertStore, Condition
from tarameteo.models import SQLModel
from tarameteo.sensors import WeatherReading


@pytest.fixture
def alert_store():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    db = Session(engine)
    yield AlertStore(db)
    db.close()
    engine.dispose()


@pytest.fixture
def notifier():
    return AsyncMock()


def _alert(**kwargs) -> Alert:
    defaults = {
        "id": "a1",
        "email": "user@example.com",
        "sensor": "outdoor-north",
        "field": "temperature",
        "condition": Condition.below,
        "threshold": -20.0,
        "confirmed": True,
    }
    defaults.update(kwargs)
    return Alert(**defaults)


def _reading(**kwargs) -> WeatherReading:
    defaults = {
        "sensor": "outdoor-north",
        "timestamp": datetime.now(UTC),
        "temperature": -25.0,
        "humidity": 80.0,
        "pressure": 1013.0,
        "latitude": 46.0,
        "longitude": -75.0,
    }
    defaults.update(kwargs)
    return WeatherReading(**defaults)


async def _check(alert_store, notifier, **reading):
    await check_alerts(_reading(**reading), alert_store, notifier, secret="s", base_url="http://localhost")


def _subjects(notifier):
    return [call.args[1] for call in notifier.send.call_args_list]


async def test_emails_once_per_crossing_and_once_back_to_normal(alert_store, notifier):
    alert_store.create(_alert())

    # Below -20, then wobbling within the 1 °C margin, then back above -19.
    for temperature in [-19.0, -21.0, -22.0, -19.5, -20.5, -18.9, -18.0, -21.0]:
        await _check(alert_store, notifier, temperature=temperature)

    assert_that(_subjects(notifier), contains_exactly(
        "outdoor-north: temperature is -21 °C",
        "outdoor-north: temperature back to normal (-18.9 °C)",
        "outdoor-north: temperature is -21 °C",
    ))


async def test_above_clears_below_threshold_minus_margin(alert_store, notifier):
    alert_store.create(_alert(field="humidity", condition=Condition.above, threshold=90.0))

    for humidity in [95.0, 86.0, 85.0]:
        await _check(alert_store, notifier, humidity=humidity)

    assert_that(_subjects(notifier), contains_exactly(
        "outdoor-north: humidity is 95 %",
        "outdoor-north: humidity back to normal (85 %)",
    ))


async def test_skips_reading_without_the_field(alert_store, notifier):
    alert_store.create(_alert(field="rain", condition=Condition.above, threshold=5.0))

    await _check(alert_store, notifier)

    notifier.send.assert_not_called()


async def test_does_not_trigger_unconfirmed_alert(alert_store, notifier):
    alert_store.create(_alert(confirmed=False))

    await _check(alert_store, notifier, temperature=-25.0)

    notifier.send.assert_not_called()


async def test_email_has_one_click_unsubscribe(alert_store, notifier):
    alert_store.create(_alert())

    await _check(alert_store, notifier, temperature=-25.0)

    recipient, _, body, headers = notifier.send.call_args.args
    assert_that(recipient, equal_to("user@example.com"))
    assert_that(headers, has_entries(
        **{"List-Unsubscribe": starts_with("<http://localhost/api/alerts/unsubscribe/")},
        **{"List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
    ))
    assert_that(body, all_of(
        contains_string(headers["List-Unsubscribe"][1:-1]),
        contains_string("All your alerts:\nhttp://localhost/api/alerts/manage/"),
    ))


async def test_writes_in_the_alert_language(alert_store, notifier):
    alert_store.create(_alert(language="fr", threshold=-20.5))

    await _check(alert_store, notifier, temperature=-25.5)

    _, subject, body, _ = notifier.send.call_args.args
    assert_that(subject, equal_to("outdoor-north : température à -25,5 °C"))
    assert_that(body, contains_string("Votre alerte : outdoor-north : température en dessous de -20,5 °C"))


async def test_retries_when_sending_fails(alert_store, notifier):
    alert_store.create(_alert())
    notifier.send.side_effect = [OSError("smtp down"), None]

    await _check(alert_store, notifier, temperature=-25.0)
    await _check(alert_store, notifier, temperature=-25.0)
    await _check(alert_store, notifier, temperature=-25.0)

    assert_that(notifier.send.call_count, equal_to(2))
