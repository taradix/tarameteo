"""Integration tests for the fs module."""

import pytest

from tarameteo.fs import atomic_write


@pytest.mark.parametrize("mode", [
    0o000,
    0o644,
])
def test_atomic_write_mode(tmp_path, mode):
    """The mode should be set on the target path."""
    path = tmp_path / "test.txt"
    atomic_write([(path, "", mode)])
    assert path.stat().st_mode & 0xfff == mode
