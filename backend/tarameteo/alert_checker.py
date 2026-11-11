"""Threshold checking for weather alerts."""

import logging
from datetime import UTC, datetime, timedelta

from tarameteo import alert_text
from tarameteo.alerts import Alert, AlertStore, Condition
from tarameteo.notifier import Notifier
from tarameteo.sensors import WeatherReading
from tarameteo.tokens import sign_token

logger = logging.getLogger(__name__)

# How far back past the threshold a value must go to count as normal again, so a reading
# wobbling around the threshold doesn't send an email each time it crosses.
MARGINS = {"temperature": 1.0, "humidity": 5.0, "pressure": 1.0, "rain": 1.0, "snow": 1.0}


def _crossed(value: float, alert: Alert) -> bool:
    return value > alert.threshold if alert.condition == Condition.above else value < alert.threshold


def _cleared(value: float, alert: Alert) -> bool:
    margin = MARGINS[alert.field]
    if alert.condition == Condition.above:
        return value <= alert.threshold - margin
    return value >= alert.threshold + margin


def unsubscribe_url(alert: Alert, secret: str, base_url: str) -> str:
    token = sign_token({"alert_id": alert.id, "action": "unsubscribe"}, secret)
    return f"{base_url}/api/alerts/unsubscribe/{token}"


def manage_url(email: str, language: str, secret: str, base_url: str, expires_in: timedelta) -> str:
    token = sign_token(
        {"email": email.lower(), "language": language, "action": "manage"}, secret, expires_in=expires_in.total_seconds()
    )
    return f"{base_url}/api/alerts/manage/{token}"


# The manage link in alert emails lasts longer than a requested one: the email may be read days later.
ALERT_MANAGE_EXPIRY = timedelta(days=7)


async def check_alerts(
    reading: WeatherReading,
    alert_store: AlertStore,
    notifier: Notifier,
    *,
    secret: str,
    base_url: str,
) -> None:
    """Email once when a value crosses its threshold, and once when it's back to normal."""
    for alert in alert_store.list_by_sensor(reading.sensor):
        value = getattr(reading, alert.field, None)
        if value is None:
            continue
        if not alert.triggered and _crossed(value, alert):
            key = "alert"
        elif alert.triggered and _cleared(value, alert):
            key = "normal"
        else:
            continue

        url = unsubscribe_url(alert, secret, base_url)
        manage = manage_url(alert.email, alert.language, secret, base_url, ALERT_MANAGE_EXPIRY)
        subject, body = alert_text.email(alert, key, url, value, manage)
        # One-click unsubscribe (RFC 8058): the mail client POSTs to the URL.
        headers = {"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
        try:
            await notifier.send(alert.email, subject, body, headers)
        except Exception:
            # The state stays, so the next reading tries again.
            logger.exception(f"Failed to send alert {alert.id} to {alert.email}")
            continue
        alert_store.set_triggered(alert.id, key == "alert", datetime.now(UTC))
        logger.info(f"Alert {alert.id} sent {key} to {alert.email}")
