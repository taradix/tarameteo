"""Notification delivery for weather alerts."""

import logging
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib
from attrs import define

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    """Protocol for sending alert notifications."""

    async def send(self, recipient: str, subject: str, body: str) -> None: ...


@define
class SmtpNotifier:
    """Send notifications via SMTP."""

    host: str
    port: int
    username: str
    password: str
    from_address: str

    async def send(self, recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        await aiosmtplib.send(
            message,
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            start_tls=True,
        )
        logger.info(f"Sent notification to {recipient}: {subject}")
