"""Tests for tarameteo.alert_checker."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from hamcrest import (
    assert_that,
    contains_string,
    equal_to,
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


async def test_triggers_alert_when_threshold_crossed(alert_store, notifier):
    alert = Alert(
        id="a1",
        email="user@example.com",
        sensor="outdoor-north",
        field="temperature",
        condition=Condition.below,
        threshold=-20.0,
        confirmed=True,
    )
    alert_store.create(alert)

    await check_alerts(
        _reading(temperature=-25.0),
        alert_store,
        notifier,
        secret="s",
        base_url="http://localhost",
    )

    notifier.send.assert_called_once()
    call_args = notifier.send.call_args
    assert_that(call_args[0][0], equal_to("user@example.com"))
    assert_that(call_args[0][1].lower(), contains_string("temperature"))


async def test_does_not_trigger_when_threshold_not_crossed(alert_store, notifier):
    alert = Alert(
        id="a1",
        email="user@example.com",
        sensor="outdoor-north",
        field="temperature",
        condition=Condition.below,
        threshold=-20.0,
        confirmed=True,
    )
    alert_store.create(alert)

    await check_alerts(
        _reading(temperature=-10.0),
        alert_store,
        notifier,
        secret="s",
        base_url="http://localhost",
    )

    notifier.send.assert_not_called()


async def test_respects_cooldown(alert_store, notifier):
    alert = Alert(
        id="a1",
        email="user@example.com",
        sensor="outdoor-north",
        field="temperature",
        condition=Condition.below,
        threshold=-20.0,
        confirmed=True,
    )
    alert_store.create(alert)
    alert_store.update_last_triggered("a1", datetime.now(UTC))

    await check_alerts(
        _reading(temperature=-25.0),
        alert_store,
        notifier,
        secret="s",
        base_url="http://localhost",
        cooldown=timedelta(hours=1),
    )

    notifier.send.assert_not_called()


async def test_does_not_trigger_unconfirmed_alert(alert_store, notifier):
    alert = Alert(
        id="a1",
        email="user@example.com",
        sensor="outdoor-north",
        field="temperature",
        condition=Condition.below,
        threshold=-20.0,
        confirmed=False,
    )
    alert_store.create(alert)

    await check_alerts(
        _reading(temperature=-25.0),
        alert_store,
        notifier,
        secret="s",
        base_url="http://localhost",
    )

    notifier.send.assert_not_called()
