"""SQLAlchemy models."""

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    String,
)
from sqlalchemy.orm import (
    Mapped,
    declarative_base,
    mapped_column,
)
from sqlalchemy.sql import false, func

SQLModel = declarative_base()


class Alert(SQLModel):
    """A weather alert subscription."""

    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    # Exactly one recipient: an email address, or an FCM token for an app install.
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    push_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sensor: Mapped[str] = mapped_column(String(255), nullable=False)
    field: Mapped[str] = mapped_column(String(50), nullable=False)
    condition: Mapped[str] = mapped_column(String(10), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    language: Mapped[str] = mapped_column(String(2), default="en", server_default="en", nullable=False)
    # Past the threshold since the last alert, until a "back to normal" message clears it.
    triggered: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_triggered_at = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_alerts_sensor_confirmed", "sensor", "confirmed"),
        Index("idx_alerts_email", "email"),
        Index("idx_alerts_push_token", "push_token"),
    )

    def __repr__(self) -> str:
        return f"<Alert(id={self.id!r}, email={self.email!r}, sensor={self.sensor!r})>"
