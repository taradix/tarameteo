"""Integration tests for the pki_cli module."""

import pytest

from tarameteo.pki_cli import main


def test_main(api_service, tmp_path, unique):
    """The main function should generate a private key, a signed cert, and a CA cert."""
    device_id = unique("text")
    api_url = f"http://{api_service.ip}/api/certs"
    ret = main(["--output-dir", str(tmp_path), "issue", "--api-url", api_url, device_id])
    assert ret == 0

    key_path = tmp_path / f"{device_id}.key"
    cert_path = tmp_path / f"{device_id}.pem"
    ca_path = tmp_path / "ca.pem"

    assert key_path.exists()
    assert cert_path.exists()
    assert ca_path.exists()


def test_main_help(capsys):
    """The main function should output usage when asked for --help."""
    with pytest.raises(SystemExit):
        main(["--help"])

    captured = capsys.readouterr()
    assert "usage" in captured.out
