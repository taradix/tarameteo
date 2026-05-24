"""HMAC-based token signing and verification for magic links."""

import hashlib
import hmac
import json
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode


def sign_token(payload: dict, secret: str, *, expires_in: float | None = None) -> str:
    """Sign a payload and return a URL-safe token.

    Parameters
    ----------
    payload:
        Arbitrary JSON-serializable data to embed in the token.
    secret:
        HMAC secret key.
    expires_in:
        Optional expiry in seconds from now.  ``None`` means no expiry.

    Returns
    -------
    A URL-safe base64 string containing the payload and signature.
    """
    data = dict(payload)
    if expires_in is not None:
        data["exp"] = time.time() + expires_in
    encoded = urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(secret.encode(), encoded, hashlib.sha256).hexdigest()
    return f"{encoded.decode()}.{signature}"


def verify_token(token: str, secret: str) -> dict | None:
    """Verify a token and return its payload, or ``None`` if invalid/expired.

    >>> verify_token(sign_token({"id": "abc"}, "s"), "s")
    {'id': 'abc'}
    >>> verify_token("tampered.token", "s") is None
    True
    >>> verify_token(sign_token({"id": "x"}, "s", expires_in=-1), "s") is None
    True
    """
    parts = token.rsplit(".", 1)
    if len(parts) != 2:
        return None

    encoded, signature = parts
    expected = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None

    # Restore base64 padding.
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        data = json.loads(urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError):
        return None

    exp = data.pop("exp", None)
    if exp is not None and time.time() > exp:
        return None

    return data
