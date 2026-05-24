"""Weather alert schemas and store."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from attrs import define
from pydantic import BaseModel, EmailStr
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session as DBSession

from tarameteo.models import Alert as AlertRow


class Condition(StrEnum):
    above = "above"
    below = "below"


AlertField = Literal["temperature", "humidity", "pressure", "rain", "snow"]

ALERT_FIELDS: list[AlertField] = ["temperature", "humidity", "pressure", "rain", "snow"]


class Alert(BaseModel):
    """A weather alert (API representation)."""

    id: str
    email: EmailStr
    sensor: str
    field: AlertField
    condition: Condition
    threshold: float
    confirmed: bool = False
    created_at: datetime | None = None
    last_triggered_at: datetime | None = None


class AlertCreate(BaseModel):
    """Payload for creating a new alert."""

    email: EmailStr
    sensor: str
    field: AlertField
    condition: Condition
    threshold: float


@define(frozen=True)
class AlertStore:
    """SQLAlchemy-backed alert persistence."""

    db: DBSession

    def create(self, alert: Alert) -> None:
        row = AlertRow(
            id=alert.id,
            email=alert.email,
            sensor=alert.sensor,
            field=alert.field,
            condition=alert.condition,
            threshold=alert.threshold,
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

    def update_last_triggered(self, alert_id: str, triggered_at: datetime) -> None:
        self.db.execute(
            update(AlertRow)
            .where(AlertRow.id == alert_id)
            .values(last_triggered_at=triggered_at)
        )
        self.db.commit()

    @staticmethod
    def _row_to_alert(row: AlertRow) -> Alert:
        return Alert(
            id=row.id,
            email=row.email,
            sensor=row.sensor,
            field=row.field,
            condition=Condition(row.condition),
            threshold=row.threshold,
            confirmed=row.confirmed,
            created_at=row.created_at,
            last_triggered_at=row.last_triggered_at,
        )
