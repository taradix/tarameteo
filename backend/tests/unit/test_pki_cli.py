"""Unit tests for the pki_cli module."""

from datetime import (
    UTC,
    datetime,
    timedelta,
)
from pathlib import Path

import pytest
from hamcrest import (
    assert_that,
    contains_string,
    equal_to,
)

from tarameteo.pki_cli import (
    CheckResult,
    CheckStatus,
    InitResult,
    InitStatus,
)


@pytest.mark.parametrize("init_result, expected", [
    (
        InitResult(InitStatus.INITIALIZED),
        equal_to("INITIALIZED\n"),
    ),
    (
        InitResult(InitStatus.INITIALIZED, reasons=("test",)),
        contains_string("test\n"),
    ),
    (
        InitResult(InitStatus.INITIALIZED, key_path=Path()),
        contains_string("key_path:"),
    ),
    (
        InitResult(InitStatus.INITIALIZED, cert_path=Path()),
        contains_string("cert_path:"),
    ),
    (
        InitResult(InitStatus.INITIALIZED, expires_at=datetime.now(UTC)),
        contains_string("expires_at:"),
    ),
    (
        InitResult(InitStatus.INITIALIZED, serial=0),
        contains_string("serial:"),
    ),
])
def test_init_result_to_text(init_result, expected):
    assert_that(init_result.to_text(), expected)


@pytest.mark.parametrize("check_result, expected", [
    (
        CheckResult(CheckStatus.OK),
        equal_to("OK\n"),
    ),
    (
        CheckResult(CheckStatus.OK, reasons=("test",)),
        contains_string("test\n"),
    ),
    (
        CheckResult(CheckStatus.OK, expires_in=timedelta(days=1)),
        contains_string("expires_in:"),
    ),
    (
        CheckResult(CheckStatus.OK, expires_at=datetime.now(UTC)),
        contains_string("expires_at:"),
    ),
    (
        CheckResult(CheckStatus.OK, key_age=timedelta(days=1)),
        contains_string("key_age:"),
    ),
    (
        CheckResult(CheckStatus.OK, key_mtime=datetime.now(UTC)),
        contains_string("key_mtime:"),
    ),
])
def test_check_result_to_text(check_result, expected):
    assert_that(check_result.to_text(), expected)
