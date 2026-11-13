"""Tests for tarameteo.alerts."""

from datetime import UTC, datetime, timedelta

import pytest
from hamcrest import (
    assert_that,
    equal_to,
    has_length,
    has_properties,
    is_,
    none,
    not_none,
)
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tarameteo.alerts import Alert, AlertCreate, AlertStore, Condition
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


def test_set_triggered(alert_store):
    alert_store.create(_make_alert())
    now = datetime.now(UTC)
    alert_store.set_triggered("test-1", True, now)
    assert_that(alert_store.get("test-1"), has_properties(triggered=True, last_triggered_at=not_none()))
    alert_store.set_triggered("test-1", False, now)
    assert_that(alert_store.get("test-1"), has_properties(triggered=False, last_triggered_at=not_none()))


def test_delete_unconfirmed_keeps_recent_and_confirmed(alert_store):
    alert_store.create(_make_alert(id="pending"))
    alert_store.create(_make_alert(id="confirmed", confirmed=True))
    alert_store.delete_unconfirmed(datetime.now(UTC) - timedelta(days=1))
    assert_that(alert_store.count_by_email("user@example.com"), equal_to(2))
    alert_store.delete_unconfirmed(datetime.now(UTC) + timedelta(minutes=1))
    assert_that(alert_store.get("pending"), none())
    assert_that(alert_store.get("confirmed"), not_none())


def test_delete_by_email_ignores_case_and_other_addresses(alert_store):
    alert_store.create(_make_alert(id="a1", email="User@Example.com"))
    alert_store.create(_make_alert(id="a2"))
    alert_store.create(_make_alert(id="a3", email="other@example.com"))
    assert_that(alert_store.delete_by_email("user@example.com", "a3"), equal_to(0))
    assert_that(alert_store.delete_by_email("USER@example.com", "a1"), equal_to(1))
    assert_that(alert_store.delete_by_email("user@example.com"), equal_to(1))
    assert_that([a.id for a in alert_store.list_by_email("other@example.com")], equal_to(["a3"]))


def test_count_by_email(alert_store):
    alert_store.create(_make_alert(id="a1"))
    alert_store.create(_make_alert(id="a2", confirmed=True))
    alert_store.create(_make_alert(id="a3", email="other@example.com"))
    assert_that(alert_store.count_by_email("user@example.com"), equal_to(2))
    assert_that(alert_store.count_by_email("user@example.com", confirmed=False), equal_to(1))


def _push_alert(**kwargs) -> Alert:
    kwargs.setdefault("push_token", "tok-1")
    return _make_alert(email=None, confirmed=True, **kwargs)


# Neither recipient, then both.
@pytest.mark.parametrize("kwargs", [{"email": None}, {"push_token": "tok-1"}])
def test_alert_needs_exactly_one_recipient(kwargs):
    with pytest.raises(ValidationError, match="either an email or a push token"):
        _make_alert(**kwargs)


def test_token_alerts_are_checked_like_email_ones(alert_store):
    alert_store.create(_push_alert())
    assert_that(alert_store.list_by_sensor("outdoor-north"), has_length(1))
    assert_that(alert_store.get("test-1"), has_properties(email=none(), push_token="tok-1"))


def test_by_token_ignores_other_tokens_and_email_alerts(alert_store):
    alert_store.create(_push_alert(id="p1"))
    alert_store.create(_push_alert(id="p2"))
    alert_store.create(_push_alert(id="p3", push_token="tok-2"))
    alert_store.create(_make_alert(id="e1"))
    assert_that(alert_store.count_by_token("tok-1"), equal_to(2))
    assert_that([a.id for a in alert_store.list_by_token("tok-1")], equal_to(["p1", "p2"]))
    assert_that(alert_store.delete_by_token("tok-1", "p3"), equal_to(0))
    assert_that(alert_store.delete_by_token("tok-1", "p1"), equal_to(1))
    assert_that(alert_store.delete_by_token("tok-1"), equal_to(1))
    assert_that(alert_store.count_by_email("user@example.com"), equal_to(1))


@pytest.mark.parametrize("condition, threshold", [("below", 3), ("above", 0.5), ("above", 721)])
def test_offline_alert_needs_above_and_sane_hours(condition, threshold):
    with pytest.raises(ValidationError, match="offline"):
        AlertCreate(email="a@b.c", sensor="s", field="offline", condition=condition, threshold=threshold)
