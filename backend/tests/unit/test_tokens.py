"""Tests for tarameteo.tokens."""

from hamcrest import (
    assert_that,
    equal_to,
    none,
)

from tarameteo.tokens import sign_token, verify_token


def test_roundtrip():
    payload = {"alert_id": "abc123", "action": "confirm"}
    token = sign_token(payload, "secret")
    assert_that(verify_token(token, "secret"), equal_to(payload))


def test_wrong_secret_returns_none():
    token = sign_token({"id": "x"}, "secret1")
    assert_that(verify_token(token, "secret2"), none())


def test_expired_token_returns_none():
    token = sign_token({"id": "x"}, "secret", expires_in=-1)
    assert_that(verify_token(token, "secret"), none())


def test_no_expiry_stays_valid():
    token = sign_token({"id": "x"}, "secret")
    assert_that(verify_token(token, "secret"), equal_to({"id": "x"}))


def test_tampered_token_returns_none():
    token = sign_token({"id": "x"}, "secret")
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    assert_that(verify_token(tampered, "secret"), none())


def test_garbage_input_returns_none():
    assert_that(verify_token("not.a.valid.token", "secret"), none())
    assert_that(verify_token("", "secret"), none())
    assert_that(verify_token("noperiod", "secret"), none())
