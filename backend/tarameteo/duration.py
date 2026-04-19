"""Duration parser."""

import re
from datetime import timedelta

_DURATION_RE = re.compile(r"(?P<value>\d+)(?P<unit>[dhms])")

_UNIT_TO_SECONDS = {
    "d": 86400,
    "h": 3600,
    "m": 60,
    "s": 1,
}

def parse_duration(value: str) -> timedelta:
    matches = list(_DURATION_RE.finditer(value))
    if not matches:
        raise ValueError(f"Invalid duration: {value}")

    seconds = 0
    consumed = 0

    for m in matches:
        v = int(m.group("value"))
        u = m.group("unit")
        seconds += v * _UNIT_TO_SECONDS[u]
        consumed += len(m.group(0))

    if consumed != len(value):
        raise ValueError(f"Invalid duration: {value}")

    return timedelta(seconds=seconds)
