"""Notification delivery for weather alerts."""

import json
import logging
import os
import time
from base64 import b64decode, urlsafe_b64encode
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib
import httpx
from attrs import define, field
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from tarameteo.crypto import load_key

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    """Protocol for sending alert notifications."""

    async def send(self, recipient: str, subject: str, body: str, headers: dict[str, str] | None = None) -> None: ...


@define
class SmtpNotifier:
    """Send notifications via SMTP."""

    host: str
    port: int
    username: str
    password: str
    from_address: str

    async def send(self, recipient: str, subject: str, body: str, headers: dict[str, str] | None = None) -> None:
        message = EmailMessage()
        message["From"] = self.from_address
        message["To"] = recipient
        message["Subject"] = subject
        for name, value in (headers or {}).items():
            message[name] = value
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


# Firebase Cloud Messaging, HTTP v1: https://firebase.google.com/docs/cloud-messaging/send-message
FCM_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
OAUTH_URL = "https://oauth2.googleapis.com/token"
TOKEN_TTL = 3600


class Unregistered(Exception):
    """The device token is gone: the app was uninstalled, or FCM replaced the token."""


def _b64(data: bytes) -> str:
    """Base64url without padding, as JSON web tokens want it."""
    return urlsafe_b64encode(data).rstrip(b"=").decode()


@define
class FcmNotifier:
    """Push notifications to app installs through Firebase Cloud Messaging."""

    project: str
    client_email: str
    # NOTE: signs the service-account JWT here; google-auth is a dependency (and a sync one) for 15 lines.
    key: rsa.RSAPrivateKey = field(repr=False)
    client: httpx.AsyncClient
    # The access token and when it stops being usable; refreshed on demand.
    _access: tuple[str, float] = field(default=("", 0.0), repr=False)

    @classmethod
    def from_env(cls, env=os.environ) -> "FcmNotifier":
        """FCM_CREDENTIALS is the service-account JSON, base64 encoded so it fits on one line."""
        account = json.loads(b64decode(env["FCM_CREDENTIALS"]))
        return cls(
            account["project_id"],
            account["client_email"],
            load_key(account["private_key"]),
            httpx.AsyncClient(timeout=10.0),
        )

    async def _token(self) -> str:
        """A short-lived access token, granted for a JWT signed with the service-account key."""
        if time.time() < self._access[1]:
            return self._access[0]
        now = int(time.time())
        claims = {"iss": self.client_email, "scope": FCM_SCOPE, "aud": OAUTH_URL, "iat": now, "exp": now + TOKEN_TTL}
        signed = f"{_b64(json.dumps({'alg': 'RS256', 'typ': 'JWT'}).encode())}.{_b64(json.dumps(claims).encode())}"
        assertion = f"{signed}.{_b64(self.key.sign(signed.encode(), padding.PKCS1v15(), hashes.SHA256()))}"
        response = await self.client.post(OAUTH_URL, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion,
        })
        response.raise_for_status()
        granted = response.json()
        # A minute of slack, so the token can't expire between here and the send.
        self._access = (granted["access_token"], now + granted.get("expires_in", TOKEN_TTL) - 60)
        return self._access[0]

    async def send(self, recipient: str, subject: str, body: str, headers: dict[str, str] | None = None) -> None:
        """Show a notification on the install the token belongs to; headers are an email thing.

        A "notification" message is displayed by Android itself, so a backgrounded app needs no code for it.
        """
        response = await self.client.post(
            FCM_URL.format(project=self.project),
            json={"message": {"token": recipient, "notification": {"title": subject, "body": body}}},
            headers={"Authorization": f"Bearer {await self._token()}"},
        )
        # Only 404 means the token is gone; a 400 is more likely this payload being wrong.
        if response.status_code == 404:
            raise Unregistered("The push token is no longer registered")
        response.raise_for_status()
        logger.info(f"Pushed a notification: {subject}")
