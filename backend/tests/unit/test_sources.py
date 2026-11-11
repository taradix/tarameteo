"""Unit tests for source runner error policy."""

from dataclasses import dataclass
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from hamcrest import assert_that, equal_to

from tarameteo.sensors import AggregateReading
from tarameteo.source import Source
from tarameteo.sources import (
    _run_source_backfill,
    _run_source_once,
)


@dataclass
class _Sensor:
    device_id: str = "sensor-1"


class _RecoverableSource(Source):
    @property
    def _sensors(self) -> list[_Sensor]:
        return [_Sensor()]

    async def run_once(self, client, ts_writer):
        raise httpx.ConnectError("down")


class _UnexpectedSource(Source):
    @property
    def _sensors(self) -> list[_Sensor]:
        return [_Sensor()]

    async def run_once(self, client, ts_writer):
        raise RuntimeError("boom")

    async def backfill_run(self, client, ts_writer, from_year, from_month, to_year, to_month) -> None:
        raise RuntimeError("boom")


async def test_run_source_once_swallows_recoverable(memory_writer, memory_queue):
    source = _RecoverableSource()
    async with httpx.AsyncClient(timeout=1) as client:
        await _run_source_once(source, client, memory_writer, memory_queue)


async def test_run_source_once_raises_unexpected(memory_writer, memory_queue):
    source = _UnexpectedSource()
    async with httpx.AsyncClient(timeout=1) as client:
        with pytest.raises(RuntimeError, match="boom"):
            await _run_source_once(source, client, memory_writer, memory_queue)


class _AggregateSource(Source):
    async def run_once(self, client, ts_writer):
        return [AggregateReading(sensor="station", timestamp=datetime.now(UTC), rain=12.0)]


async def test_run_source_once_publishes_and_checks_alerts(memory_writer, memory_queue, monkeypatch):
    check = AsyncMock(side_effect=[OSError("db down"), None])
    monkeypatch.setattr("tarameteo.sources.check_reading", check)
    async with memory_queue.connect("weather:station") as q, httpx.AsyncClient(timeout=1) as client:
        # A failing check is logged, not raised, so the sync loop keeps going.
        for _ in range(2):
            await _run_source_once(_AggregateSource(), client, memory_writer, q, notifier=AsyncMock(), alert_secret="s")
        assert_that(AggregateReading.model_validate_json(await q.receive(1)).rain, equal_to(12.0))
    assert_that(check.call_count, equal_to(2))


async def test_run_source_backfill_raises_unexpected(memory_writer):
    source = _UnexpectedSource()
    async with httpx.AsyncClient(timeout=1) as client:
        with pytest.raises(RuntimeError, match="boom"):
            await _run_source_backfill(source, client, memory_writer, 2025, 1, 2025, 1)
