"""Unit tests for source runner error policy."""

from dataclasses import dataclass

import httpx
import pytest

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

    async def run_once(self, client, ts_writer, queue) -> None:
        raise httpx.ConnectError("down")


class _UnexpectedSource(Source):
    @property
    def _sensors(self) -> list[_Sensor]:
        return [_Sensor()]

    async def run_once(self, client, ts_writer, queue) -> None:
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


async def test_run_source_backfill_raises_unexpected(memory_writer):
    source = _UnexpectedSource()
    async with httpx.AsyncClient(timeout=1) as client:
        with pytest.raises(RuntimeError, match="boom"):
            await _run_source_backfill(source, client, memory_writer, 2025, 1, 2025, 1)
