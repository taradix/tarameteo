"""Certificate Authority (CA) service."""

import os
import secrets
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
)

from tarameteo.ca_client import (
    IssueCertificateRequest,
    IssueCertificateResponse,
)
from tarameteo.pki import sign_csr_pem

app = FastAPI(
    title="TaraMeteo Certificate Authority",
)

CA_KEY = Path(os.getenv("CA_KEY", "/ca/ca.key"))
CA_CERT = Path(os.getenv("CA_CERT", "/ca/ca.pem"))


def require_token(authorization: str | None = Header(default=None), env = os.environ) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    expected = env["CA_TOKEN"]
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="Invalid token")


@app.post("/v1/certs", response_model=IssueCertificateResponse, dependencies=[Depends(require_token)])
def issue_cert(request: IssueCertificateRequest) -> IssueCertificateResponse:
    ca_cert_pem = CA_CERT.read_text()
    ca_key_pem = CA_KEY.read_text()

    try:
        return sign_csr_pem(
            csr_pem=request.csr_pem,
            ca_cert_pem=ca_cert_pem,
            ca_key_pem=ca_key_pem,
            client_auth=request.client_auth,
            server_auth=request.server_auth,
            ttl_days=request.ttl_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/healthz", include_in_schema=False)
def get_healthz() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
