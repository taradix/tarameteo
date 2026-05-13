"""Unit tests for the Source base class."""

from dataclasses import dataclass

import pytest

from tarameteo.metar import MetarSource
from tarameteo.source import Source


@dataclass
class _Sensor:
    device_id: str


class _MonthBackfillSource(Source):
    """Minimal concrete Source that records _backfill_month calls."""

    def __init__(self, sensors: list[_Sensor]) -> None:
        self._mock_sensors = sensors
        self.calls: list[tuple[str, int, int]] = []

    @property
    def _sensors(self) -> list[_Sensor]:
        return self._mock_sensors

    async def run_once(self, client, ts_writer, queue) -> None:
        pass

    async def _backfill_month(self, client, sensor, year, month, ts_writer) -> None:
        self.calls.append((sensor.device_id, year, month))


async def test_backfill_run_iterates_months() -> None:
    sensor = _Sensor("dev-1")
    src = _MonthBackfillSource([sensor])
    await src.backfill_run(None, None, 2024, 11, 2025, 1)
    assert src.calls == [
        ("dev-1", 2024, 11),
        ("dev-1", 2024, 12),
        ("dev-1", 2025, 1),
    ]


async def test_backfill_run_single_month() -> None:
    sensor = _Sensor("dev-1")
    src = _MonthBackfillSource([sensor])
    await src.backfill_run(None, None, 2025, 3, 2025, 3)
    assert src.calls == [("dev-1", 2025, 3)]


async def test_backfill_run_multiple_sensors() -> None:
    sensors = [_Sensor("dev-1"), _Sensor("dev-2")]
    src = _MonthBackfillSource(sensors)
    await src.backfill_run(None, None, 2025, 1, 2025, 2)
    assert src.calls == [
        ("dev-1", 2025, 1),
        ("dev-1", 2025, 2),
        ("dev-2", 2025, 1),
        ("dev-2", 2025, 2),
    ]


async def test_backfill_run_continues_after_error() -> None:
    """A failing month does not abort the remaining months."""
    sensor = _Sensor("dev-1")
    src = _MonthBackfillSource([sensor])

    original = src._backfill_month
    call_count = 0

    async def _fail_first(client, sensor, year, month, ts_writer):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("network error")
        await original(client, sensor, year, month, ts_writer)

    src._backfill_month = _fail_first  # type: ignore[method-assign]
    await src.backfill_run(None, None, 2025, 1, 2025, 3)
    # First month failed, months 2 and 3 succeeded
    assert src.calls == [("dev-1", 2025, 2), ("dev-1", 2025, 3)]


async def test_backfill_run_year_rollover() -> None:
    sensor = _Sensor("dev-1")
    src = _MonthBackfillSource([sensor])
    await src.backfill_run(None, None, 2024, 12, 2025, 2)
    assert src.calls == [
        ("dev-1", 2024, 12),
        ("dev-1", 2025, 1),
        ("dev-1", 2025, 2),
    ]


async def test_metar_backfill_run_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """MetarSource.backfill_run should log a warning, not raise."""
    src = MetarSource()
    with caplog.at_level("WARNING"):
        await src.backfill_run(None, None, 2025, 1, 2025, 1)
    assert any("not supported" in r.message for r in caplog.records)
