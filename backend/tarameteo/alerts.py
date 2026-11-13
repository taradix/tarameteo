"""Weather alert schemas and store."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from attrs import define
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session as DBSession

from tarameteo.models import Alert as AlertRow


class Condition(StrEnum):
    above = "above"
    below = "below"


# "offline": no reading for more than threshold hours.
AlertField = Literal["temperature", "humidity", "pressure", "rain", "snow", "offline"]

ALERT_FIELDS: list[AlertField] = ["temperature", "humidity", "pressure", "rain", "snow", "offline"]

# Sensor readings are only looked this far back, so an offline alert can't wait longer.
OFFLINE_MAX_HOURS = 30 * 24

Language = Literal["en", "fr"]


class Alert(BaseModel):
    """A weather alert (API representation)."""

    id: str
    # Exactly one recipient: an address to email, or an FCM token to push to.
    email: EmailStr | None = None
    push_token: str | None = None
    sensor: str
    field: AlertField
    condition: Condition
    threshold: float
    language: Language = "en"
    confirmed: bool = False
    triggered: bool = False
    created_at: datetime | None = None
    last_triggered_at: datetime | None = None

    @model_validator(mode="after")
    def _one_recipient(self) -> "Alert":
        if bool(self.email) == bool(self.push_token):
            raise ValueError("An alert needs either an email or a push token, not both")
        return self


class AlertCreate(BaseModel):
    """Payload for creating a new alert."""

    email: EmailStr
    sensor: str
    field: AlertField
    condition: Condition
    threshold: float = Field(description='For "offline", hours without a reading; the condition must be "above"')
    language: Language = "en"

    @model_validator(mode="after")
    def _check_offline(self) -> "AlertCreate":
        if self.field == "offline" and (self.condition != Condition.above or not 1 <= self.threshold <= OFFLINE_MAX_HOURS):
            raise ValueError(f'An offline alert needs condition "above" and 1 to {OFFLINE_MAX_HOURS} hours')
        return self


class ManageRequest(BaseModel):
    """Payload for emailing a link to manage an address's alerts."""

    email: EmailStr
    language: Language = "en"


def _same_email(email: str):
    # People don't type their address the same way twice.
    return func.lower(AlertRow.email) == email.lower()


@define(frozen=True)
class AlertStore:
    """SQLAlchemy-backed alert persistence."""

    db: DBSession

    def create(self, alert: Alert) -> None:
        row = AlertRow(
            id=alert.id,
            email=alert.email,
            push_token=alert.push_token,
            sensor=alert.sensor,
            field=alert.field,
            condition=alert.condition,
            threshold=alert.threshold,
            language=alert.language,
            confirmed=alert.confirmed,
        )
        self.db.add(row)
        self.db.commit()

    def confirm(self, alert_id: str) -> bool:
        result = self.db.execute(
            update(AlertRow)
            .where(AlertRow.id == alert_id, AlertRow.confirmed == False)  # noqa: E712
            .values(confirmed=True)
        )
        self.db.commit()
        return result.rowcount > 0

    def delete(self, alert_id: str) -> bool:
        result = self.db.execute(
            delete(AlertRow).where(AlertRow.id == alert_id)
        )
        self.db.commit()
        return result.rowcount > 0

    def delete_unconfirmed(self, before: datetime) -> None:
        """Drop alerts whose confirm link has expired."""
        self.db.execute(
            delete(AlertRow).where(AlertRow.confirmed == False, AlertRow.created_at < before)  # noqa: E712
        )
        self.db.commit()

    def count_by_email(self, email: str, *, confirmed: bool | None = None) -> int:
        query = select(func.count()).select_from(AlertRow).where(_same_email(email))
        if confirmed is not None:
            query = query.where(AlertRow.confirmed == confirmed)
        return self.db.execute(query).scalar_one()

    def list_by_email(self, email: str) -> list[Alert]:
        rows = self.db.execute(
            select(AlertRow).where(_same_email(email)).order_by(AlertRow.sensor, AlertRow.created_at)
        ).scalars().all()
        return [self._row_to_alert(row) for row in rows]

    def delete_by_email(self, email: str, alert_id: str | None = None) -> int:
        """Delete one of the email's alerts, or all of them."""
        query = delete(AlertRow).where(_same_email(email))
        if alert_id is not None:
            query = query.where(AlertRow.id == alert_id)
        result = self.db.execute(query)
        self.db.commit()
        return result.rowcount

    # An email alert's push_token is NULL, which never equals a token, so these can't touch one.
    def count_by_token(self, token: str) -> int:
        return self.db.execute(
            select(func.count()).select_from(AlertRow).where(AlertRow.push_token == token)
        ).scalar_one()

    def list_by_token(self, token: str) -> list[Alert]:
        rows = self.db.execute(
            select(AlertRow).where(AlertRow.push_token == token).order_by(AlertRow.sensor, AlertRow.created_at)
        ).scalars().all()
        return [self._row_to_alert(row) for row in rows]

    def delete_by_token(self, token: str, alert_id: str | None = None) -> int:
        """Delete one of the token's alerts, or all of them (the install is gone)."""
        query = delete(AlertRow).where(AlertRow.push_token == token)
        if alert_id is not None:
            query = query.where(AlertRow.id == alert_id)
        result = self.db.execute(query)
        self.db.commit()
        return result.rowcount

    def get(self, alert_id: str) -> Alert | None:
        row = self.db.execute(
            select(AlertRow).where(AlertRow.id == alert_id)
        ).scalar_one_or_none()
        return self._row_to_alert(row) if row else None

    def list_by_sensor(self, sensor: str) -> list[Alert]:
        rows = self.db.execute(
            select(AlertRow).where(AlertRow.sensor == sensor, AlertRow.confirmed == True)  # noqa: E712
        ).scalars().all()
        return [self._row_to_alert(row) for row in rows]

    def list_offline(self) -> list[Alert]:
        """Confirmed offline alerts that haven't fired yet."""
        rows = self.db.execute(
            select(AlertRow).where(
                AlertRow.field == "offline", AlertRow.confirmed == True, AlertRow.triggered == False  # noqa: E712
            )
        ).scalars().all()
        return [self._row_to_alert(row) for row in rows]

    def set_triggered(self, alert_id: str, triggered: bool, at: datetime) -> None:
        values = {"triggered": triggered}
        if triggered:
            values["last_triggered_at"] = at
        self.db.execute(update(AlertRow).where(AlertRow.id == alert_id).values(**values))
        self.db.commit()

    @staticmethod
    def _row_to_alert(row: AlertRow) -> Alert:
        return Alert(
            id=row.id,
            email=row.email,
            push_token=row.push_token,
            sensor=row.sensor,
            field=row.field,
            condition=Condition(row.condition),
            threshold=row.threshold,
            language=row.language,
            confirmed=row.confirmed,
            triggered=row.triggered,
            created_at=row.created_at,
            last_triggered_at=row.last_triggered_at,
        )
