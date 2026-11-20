"""Unit tests for the pki_cli module."""

from datetime import (
    UTC,
    datetime,
)
from pathlib import Path

import pytest
from hamcrest import (
    assert_that,
    contains_string,
    equal_to,
)

from tarameteo.pki_cli import (
    InitResult,
    InitStatus,
    main,
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


@pytest.mark.parametrize("argv, error", [
    pytest.param([], "the following arguments are required: command", id="no command"),
    pytest.param(["init", "--ttl-days", "0"], "ttl_days must be in", id="init ttl zero"),
    pytest.param(["init", "--ttl-days", "-1"], "ttl_days must be in", id="init ttl negative"),
])
def test_main_rejects_invalid_args(argv, error, tmp_path, capsys):
    with pytest.raises(SystemExit):
        main(["--output-dir", str(tmp_path), *argv])

    assert_that(capsys.readouterr().err, contains_string(error))
