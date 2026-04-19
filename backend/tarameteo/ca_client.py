"""Certificate Authority (CA) client."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from json import JSONDecodeError

import httpx
from attrs import define
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
)
from yarl import URL

from tarameteo.pki import CertificateMaterial

TTL_MIN = 1
TTL_MAX = 365


def validate_ttl_days(value: int | None) -> int | None:
    if value is not None and not (TTL_MIN <= value <= TTL_MAX):
        raise ValueError(f"ttl_days must be in [{TTL_MIN}, {TTL_MAX}], got {value}")
    return value


class IssueCertificateRequest(BaseModel):
    """Request to a Certificate Authority (CA) to issue an X.509 certificate."""

    csr_pem: str = Field(min_length=1)
    ttl_days: int | None = Field(None, ge=TTL_MIN, le=TTL_MAX)
    client_auth: bool = True
    server_auth: bool = False

    _validate_ttl_days = field_validator("ttl_days")(validate_ttl_days)


IssueCertificateResponse = CertificateMaterial


@define(frozen=True)
class IssueCertificateError(Exception):

    message: str
    method: str
    url: str
    status_code: int | None = None
    reason: str | None = None

    def __str__(self) -> str:
        parts = [self.message]
        parts.append(f"{self.method} {self.url}")
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.reason is not None:
            parts.append(f"reason={self.reason}")
        return " | ".join(parts)


@define(frozen=True)
class CAClient:

    client: httpx.Client
    path: str

    @classmethod
    @contextmanager
    def from_url(cls, url: URL | str, token: str | None = None, timeout: float = 10.0):
        url = URL(url)
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"

        with httpx.Client(
            base_url=str(url.origin()),
            headers=headers,
            timeout=timeout,
        ) as client:
            yield cls(client, url.path)

    def issue_certificate(self, request: IssueCertificateRequest) -> IssueCertificateResponse:
        try:
            response = self.client.post(self.path, json=request.model_dump())
            response.raise_for_status()

        except httpx.HTTPStatusError as e:
            r = e.response
            try:
                reason = f"Detail: {r.json()}"
            except JSONDecodeError:
                reason = f"Response: {r.text}"

            raise IssueCertificateError(
                message="CA rejected certificate request",
                method=r.request.method,
                url=str(r.request.url),
                status_code=r.status_code,
                reason=reason,
            ) from e

        except httpx.TimeoutException as e:
            r = e.request
            raise IssueCertificateError(
                message="Timeout while requesting certificate",
                method=r.method,
                url=str(r.url),
            ) from e

        except httpx.RequestError as e:
            r = e.request
            raise IssueCertificateError(
                message=f"Network error while requesting certificate: {type(e).__name__}",
                method=r.method,
                url=str(r.url),
            ) from e

        try:
            data = response.json()
        except JSONDecodeError as e:
            raise IssueCertificateError(
                message="CA returned non-JSON response",
                method=response.request.method,
                url=str(response.request.url),
                status_code=response.status_code,
                reason=response.text,
            ) from e

        try:
            return IssueCertificateResponse.model_validate(data)
        except ValidationError as e:
            raise IssueCertificateError(
                message="CA response JSON missing expected fields",
                method=response.request.method,
                url=str(response.request.url),
                status_code=response.status_code,
                reason=str(e),
            ) from e


def get_ca_client(env = os.environ) -> Iterator[CAClient]:
    url = env["CA_URL"]
    token = env["CA_TOKEN"]
    with CAClient.from_url(url, token) as ca_client:
        yield ca_client

