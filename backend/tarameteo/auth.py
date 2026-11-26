"""Bearer token checks for the API and CA services."""

import os
import secrets
from collections.abc import Mapping
from typing import Annotated

from fastapi import Depends, Header, HTTPException


def bearer_token(name: str):
    """A dependency that requires the bearer token held in the environment variable name."""

    def require(
        authorization: str | None = Header(default=None),
        env: Annotated[Mapping[str, str], Depends(lambda: os.environ)] = os.environ,
    ) -> None:
        expected = env.get(name, "")
        if not expected:
            raise HTTPException(status_code=503, detail=f"{name} is not configured")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        token = authorization.removeprefix("Bearer ").strip()
        if not secrets.compare_digest(token, expected):
            raise HTTPException(status_code=403, detail="Invalid token")

    return require
