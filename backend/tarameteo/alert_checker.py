"""Alert emails: threshold checks on readings, and the links in every alert email."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from attrs import define

from tarameteo import alert_text
from tarameteo.alerts import OFFLINE_MAX_HOURS, Alert, AlertStore, Condition
from tarameteo.db import SessionLocal
from tarameteo.notifier import Notifier
from tarameteo.sensors import AGGREGATE_MEASUREMENT, MEASUREMENT, SENSOR_TAG, AggregateReading, WeatherReading
from tarameteo.tokens import sign_token, verify_token
from tarameteo.ts import TSReader

logger = logging.getLogger(__name__)

# How far back past the threshold a value must go to count as normal again, so a reading
# wobbling around the threshold doesn't send an email each time it crosses.
MARGINS = {"temperature": 1.0, "humidity": 5.0, "pressure": 1.0, "rain": 1.0, "snow": 1.0}

CONFIRM_EXPIRY = timedelta(days=1)
# The manage link in alert emails lasts longer than a requested one: the email may be read days later.
ALERT_MANAGE_EXPIRY = timedelta(days=7)
MANAGE_EXPIRY = timedelta(hours=1)


def _crossed(value: float, alert: Alert) -> bool:
    return value > alert.threshold if alert.condition == Condition.above else value < alert.threshold


def _value(reading: WeatherReading | AggregateReading, alert: Alert) -> float | None:
    # A daily aggregate crosses "above" with its maximum and "below" with its minimum; rain and snow are totals.
    if isinstance(reading, AggregateReading) and alert.field not in ("rain", "snow"):
        return getattr(reading, f"{alert.field}_{'max' if alert.condition == Condition.above else 'min'}")
    return getattr(reading, alert.field, None)


def _cleared(value: float, alert: Alert) -> bool:
    margin = MARGINS[alert.field]
    if alert.condition == Condition.above:
        return value <= alert.threshold - margin
    return value >= alert.threshold + margin


@define(frozen=True)
class AlertService:
    """Sends every alert email, and signs and verifies the links in them."""

    notifier: Notifier
    secret: str
    base_url: str

    def _url(self, action: str, payload: dict, expires_in: timedelta | None = None) -> str:
        token = sign_token({**payload, "action": action}, self.secret, expires_in=expires_in and expires_in.total_seconds())
        return f"{self.base_url}/api/alerts/{action}/{token}"

    def verify(self, token: str, action: str) -> dict | None:
        """The token's payload, if it's valid and signed for this action."""
        payload = verify_token(token, self.secret)
        return payload if payload and payload.get("action") == action else None

    async def send_confirm(self, alert: Alert) -> None:
        url = self._url("confirm", {"alert_id": alert.id}, CONFIRM_EXPIRY)
        await self.notifier.send(alert.email, *alert_text.email(alert, "confirm", url))

    async def send_manage(self, email: str, language: str) -> None:
        url = self._url("manage", {"email": email.lower(), "language": language}, MANAGE_EXPIRY)
        text = alert_text.TEXT[language]
        await self.notifier.send(email, text["manage_subject"], text["manage_body"].format(url=url))

    async def _notify(self, alert: Alert, key: str, value: float | None, alert_store: AlertStore) -> None:
        url = self._url("unsubscribe", {"alert_id": alert.id})
        manage = self._url("manage", {"email": alert.email.lower(), "language": alert.language}, ALERT_MANAGE_EXPIRY)
        subject, body = alert_text.email(alert, key, url, value, manage)
        # One-click unsubscribe (RFC 8058): the mail client POSTs to the URL.
        headers = {"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
        try:
            await self.notifier.send(alert.email, subject, body, headers)
        except Exception:
            # The state stays, so the next check tries again.
            logger.exception(f"Failed to send alert {alert.id} to {alert.email}")
            return
        alert_store.set_triggered(alert.id, key in ("alert", "offline"), datetime.now(UTC))
        logger.info(f"Alert {alert.id} sent {key} to {alert.email}")

    async def check(self, reading: WeatherReading | AggregateReading, alert_store: AlertStore) -> None:
        """Email once when a value crosses its threshold, and once when it's back to normal."""
        for alert in alert_store.list_by_sensor(reading.sensor):
            if alert.field == "offline":
                # Sources re-send their last reading on startup, so only a recent one means it's back.
                if alert.triggered and datetime.now(UTC) - reading.timestamp <= timedelta(hours=alert.threshold):
                    await self._notify(alert, "online", None, alert_store)
                continue
            value = _value(reading, alert)
            if value is None:
                continue
            if not alert.triggered and _crossed(value, alert):
                await self._notify(alert, "alert", value, alert_store)
            elif alert.triggered and _cleared(value, alert):
                await self._notify(alert, "normal", value, alert_store)

    async def check_offline(self, last_seen: dict[str, datetime], alert_store: AlertStore) -> None:
        """Email once when a sensor's last reading is older than its alert's hours; check() says when it's back."""
        now = datetime.now(UTC)
        for alert in alert_store.list_offline():
            seen = last_seen.get(alert.sensor)
            hours = (now - seen).total_seconds() / 3600 if seen else alert.threshold
            if seen is None or hours > alert.threshold:
                await self._notify(alert, "offline", round(hours), alert_store)

    async def check_reading(self, reading: WeatherReading | AggregateReading) -> None:
        """Check a reading against its sensor's alerts in a session of its own."""
        db = SessionLocal()
        try:
            await self.check(reading, AlertStore(db))
        finally:
            db.close()


OFFLINE_EVERY = timedelta(minutes=10)


def last_seen(ts_reader: TSReader, start: datetime) -> dict[str, datetime]:
    """Each sensor's latest reading time, live or aggregate."""
    seen: dict[str, datetime] = {}
    for measurement in (MEASUREMENT, AGGREGATE_MEASUREMENT):
        for p in ts_reader.last_points(measurement=measurement, start=start):
            if name := p.tags.get(SENSOR_TAG):
                seen[name] = max(seen.get(name, p.timestamp), p.timestamp)
    return seen


async def run_offline_checks(alerts: AlertService, ts_reader: TSReader) -> None:
    """Check offline alerts every few minutes, until cancelled."""
    while True:
        try:
            # ponytail: reads every sensor's last point each time; query only alerted sensors if that gets slow.
            seen = await asyncio.to_thread(last_seen, ts_reader, datetime.now(UTC) - timedelta(hours=OFFLINE_MAX_HOURS))
            db = SessionLocal()
            try:
                await alerts.check_offline(seen, AlertStore(db))
            finally:
                db.close()
        except Exception:
            logger.exception("Failed to check offline alerts")
        await asyncio.sleep(OFFLINE_EVERY.total_seconds())
