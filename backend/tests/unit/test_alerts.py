"""Tests for tarameteo.alerts."""

from datetime import UTC, datetime

import pytest
from hamcrest import (
    assert_that,
    has_length,
    has_properties,
    is_,
    none,
    not_none,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tarameteo.alerts import Alert, AlertStore, Condition
from tarameteo.models import SQLModel


@pytest.fixture
def alert_store():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    db = Session(engine)
    yield AlertStore(db)
    db.close()
    engine.dispose()


def _make_alert(**kwargs) -> Alert:
    defaults = {
        "id": "test-1",
        "email": "user@example.com",
        "sensor": "outdoor-north",
        "field": "temperature",
        "condition": Condition.below,
        "threshold": -20.0,
    }
    defaults.update(kwargs)
    return Alert(**defaults)


def test_create_and_get(alert_store):
    alert_store.create(_make_alert())
    result = alert_store.get("test-1")
    assert_that(result, has_properties(email="user@example.com", confirmed=False))


def test_confirm(alert_store):
    alert_store.create(_make_alert())
    assert_that(alert_store.confirm("test-1"), is_(True))
    assert_that(alert_store.get("test-1"), has_properties(confirmed=True))


def test_confirm_already_confirmed_returns_false(alert_store):
    alert_store.create(_make_alert())
    alert_store.confirm("test-1")
    assert_that(alert_store.confirm("test-1"), is_(False))


def test_delete(alert_store):
    alert_store.create(_make_alert())
    assert_that(alert_store.delete("test-1"), is_(True))
    assert_that(alert_store.get("test-1"), none())


def test_delete_nonexistent_returns_false(alert_store):
    assert_that(alert_store.delete("nope"), is_(False))


def test_list_by_sensor_only_confirmed(alert_store):
    alert_store.create(_make_alert(id="a1", confirmed=False))
    alert_store.create(_make_alert(id="a2", confirmed=True))
    results = alert_store.list_by_sensor("outdoor-north")
    assert_that(results, has_length(1))
    assert_that(results[0], has_properties(id="a2"))


def test_update_last_triggered(alert_store):
    alert_store.create(_make_alert())
    now = datetime.now(UTC)
    alert_store.update_last_triggered("test-1", now)
    assert_that(alert_store.get("test-1").last_triggered_at, not_none())
