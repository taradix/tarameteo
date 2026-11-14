"""Tests for tarameteo.notifier."""

import json
from base64 import b64encode, urlsafe_b64decode
from urllib.parse import parse_qs

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from hamcrest import assert_that, contains_exactly, contains_string, equal_to, has_entries

from tarameteo.crypto import KeyAlgorithm, KeySpec, generate_key_pem, load_key
from tarameteo.notifier import FcmNotifier, Unregistered

# One key for the whole file: generating RSA keys isn't free.
KEY_PEM = generate_key_pem(KeySpec(KeyAlgorithm.RSA))


def _notifier(requests: list, fcm_status: int = 200) -> FcmNotifier:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "at-1", "expires_in": 3600})
        return httpx.Response(fcm_status, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return FcmNotifier("proj", "svc@proj.iam.gserviceaccount.com", load_key(KEY_PEM), client)


def _unpad(encoded: str) -> bytes:
    return urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))


async def test_signs_a_jwt_for_an_access_token_then_pushes():
    requests = []

    await _notifier(requests).send("tok-1", "outdoor: temperature is -25 °C", "outdoor: temperature below -20 °C")

    grant, push = requests
    assertion = parse_qs(grant.content.decode())["assertion"][0]
    signed, _, signature = assertion.rpartition(".")
    # The real Google would reject anything we signed wrong, so check the signature here.
    load_key(KEY_PEM).public_key().verify(_unpad(signature), signed.encode(), padding.PKCS1v15(), hashes.SHA256())
    assert_that(json.loads(_unpad(signed.split(".")[0])), has_entries(alg="RS256", typ="JWT"))
    assert_that(json.loads(_unpad(signed.split(".")[1])), has_entries(
        iss="svc@proj.iam.gserviceaccount.com",
        aud="https://oauth2.googleapis.com/token",
        scope=contains_string("firebase.messaging"),
    ))

    assert_that(str(push.url), equal_to("https://fcm.googleapis.com/v1/projects/proj/messages:send"))
    assert_that(push.headers["Authorization"], equal_to("Bearer at-1"))
    assert_that(json.loads(push.content), equal_to({"message": {
        "token": "tok-1",
        "notification": {"title": "outdoor: temperature is -25 °C", "body": "outdoor: temperature below -20 °C"},
    }}))


async def test_reuses_the_access_token():
    requests = []
    notifier = _notifier(requests)

    await notifier.send("tok-1", "a subject", "a body")
    await notifier.send("tok-1", "a subject", "a body")

    assert_that([r.url.host for r in requests], contains_exactly(
        "oauth2.googleapis.com", "fcm.googleapis.com", "fcm.googleapis.com",
    ))


async def test_a_gone_token_is_unregistered():
    with pytest.raises(Unregistered):
        await _notifier([], fcm_status=404).send("tok-1", "a subject", "a body")


async def test_other_failures_are_not():
    # A rejected payload is this code being wrong, not the install being gone.
    with pytest.raises(httpx.HTTPStatusError):
        await _notifier([], fcm_status=400).send("tok-1", "a subject", "a body")


async def test_from_env_reads_a_base64_service_account():
    account = {"project_id": "proj", "client_email": "svc@example.com", "private_key": KEY_PEM}
    credentials = b64encode(json.dumps(account).encode()).decode()

    notifier = FcmNotifier.from_env({"FCM_CREDENTIALS": credentials})

    assert_that(notifier.project, equal_to("proj"))
    assert_that(notifier.client_email, equal_to("svc@example.com"))
    await notifier.client.aclose()
