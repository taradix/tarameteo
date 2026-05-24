"""Threshold checking for weather alerts."""

import logging
from datetime import UTC, datetime, timedelta

from tarameteo.alerts import AlertStore, Condition
from tarameteo.notifier import Notifier
from tarameteo.sensors import WeatherReading
from tarameteo.tokens import sign_token

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN = timedelta(hours=1)


def _evaluate_condition(value: float | None, condition: Condition, threshold: float) -> bool:
    if value is None:
        return False
    if condition == Condition.above:
        return value > threshold
    return value < threshold


def _ensure_utc(dt: datetime | None) -> datetime | None:
    """Ensure a datetime is timezone-aware (UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def check_alerts(
    reading: WeatherReading,
    alert_store: AlertStore,
    notifier: Notifier,
    *,
    secret: str,
    base_url: str,
    cooldown: timedelta = DEFAULT_COOLDOWN,
) -> None:
    """Check active alerts for a sensor and send notifications if triggered."""
    alerts = alert_store.list_by_sensor(reading.sensor)
    now = datetime.now(UTC)

    for alert in alerts:
        # Respect cooldown.
        last_triggered = _ensure_utc(alert.last_triggered_at)
        if last_triggered and (now - last_triggered) < cooldown:
            continue

        value = getattr(reading, alert.field, None)
        if not _evaluate_condition(value, alert.condition, alert.threshold):
            continue

        # Build unsubscribe link.
        token = sign_token({"alert_id": alert.id, "action": "unsubscribe"}, secret)
        unsubscribe_url = f"{base_url}/api/alerts/unsubscribe/{token}"

        subject = f"Weather alert: {alert.field} is {value}"
        body = (
            f"Your alert has been triggered.\n\n"
            f"Sensor: {reading.sensor}\n"
            f"{alert.field.capitalize()}: {value}\n"
            f"Condition: {alert.condition} {alert.threshold}\n\n"
            f"To unsubscribe from this alert:\n{unsubscribe_url}\n"
        )

        try:
            await notifier.send(alert.email, subject, body)
            alert_store.update_last_triggered(alert.id, now)
            logger.info(f"Alert {alert.id} triggered for {alert.email}")
        except Exception:
            logger.exception(f"Failed to send alert {alert.id} to {alert.email}")
