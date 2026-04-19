"""API service."""

import logging
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    Request,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from tarameteo.ca_client import (
    CAClient,
    IssueCertificateRequest,
    IssueCertificateResponse,
    get_ca_client,
)

logger = logging.getLogger("uvicorn")
app = FastAPI(
    title="TaraMeteo API",
    docs_url="/api/swagger",
    openapi_url="/api/openapi.json",
)

origins = [
    "http://172.22.1.5",
    "http://localhost",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/certs", response_model=IssueCertificateResponse)
def post_cert(
    request: IssueCertificateRequest,
    ca_client: Annotated[CAClient, Depends(get_ca_client)],
) -> IssueCertificateResponse:
    return ca_client.issue_certificate(request)


@app.exception_handler(Exception)
async def exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception at {request.url}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


@app.get("/healthz", include_in_schema=False)
def get_healthz() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
