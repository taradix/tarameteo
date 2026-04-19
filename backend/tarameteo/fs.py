"""Filesystem utilities."""

import os
from pathlib import Path
from tempfile import mkstemp


def atomic_write(path: Path | str, content: str, *, mode: int = 0o644) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = mkstemp(prefix=path.name + ".", dir=str(path.parent))
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        tmp_path.chmod(mode)
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)
