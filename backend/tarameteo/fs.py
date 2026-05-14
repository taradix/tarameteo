"""Filesystem utilities."""

import os
from pathlib import Path
from tempfile import mkstemp


def _stage_write(path: Path, content: str, mode: int) -> Path:
    """Write content to a temp file alongside *path*. Return the temp path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = mkstemp(prefix=path.name + ".", dir=str(path.parent))
    tmp_path = Path(tmp)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    tmp_path.chmod(mode)
    return tmp_path


def atomic_write(writes: list[tuple[Path | str, str, int]]) -> None:
    """Write files atomically as a group.

    All files are staged (written to temp files) first. Only once all
    staging succeeds are the temp files renamed to their final paths.
    If any staging step fails, all temp files are cleaned up and no
    target file is modified.

    Each entry in *writes* is (path, content, mode).
    """
    staged: list[tuple[Path, Path]] = []
    try:
        for dest, content, mode in writes:
            dest = Path(dest)
            tmp_path = _stage_write(dest, content, mode)
            staged.append((tmp_path, dest))

        for tmp_path, dest in staged:
            tmp_path.replace(dest)
        staged.clear()
    finally:
        for tmp_path, _ in staged:
            tmp_path.unlink(missing_ok=True)
