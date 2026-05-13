"""Abstract base class for external weather sources."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx
from taraqueue import Queue

from tarameteo.ts import TSWriter

logger = logging.getLogger(__name__)


class Source(ABC):
    """Base class for external weather data sources."""

    @property
    def name(self) -> str:
        """Human-readable source name used in log messages."""
        return type(self).__name__

    @abstractmethod
    async def run_once(
        self,
        client: httpx.AsyncClient,
        ts_writer: TSWriter,
        queue: Queue,
    ) -> None:
        """Fetch and store the current data for all sensors."""

    @property
    def _sensors(self) -> list[Any]:
        raise NotImplementedError(f"{self.name} must implement _sensors or override backfill_run")

    async def _backfill_month(
        self,
        client: httpx.AsyncClient,
        sensor: Any,
        year: int,
        month: int,
        ts_writer: TSWriter,
    ) -> None:
        raise NotImplementedError(f"{self.name} must implement _backfill_month or override backfill_run")

    async def backfill_run(
        self,
        client: httpx.AsyncClient,
        ts_writer: TSWriter,
        from_year: int,
        from_month: int,
        to_year: int,
        to_month: int,
    ) -> None:
        """Backfill historical data over the given month range for all sensors."""
        for sensor in self._sensors:
            year, month = from_year, from_month
            while (year, month) <= (to_year, to_month):
                logger.info(
                    "%s %s: backfilling %d-%02d",
                    self.name, sensor.device_id, year, month,
                )
                try:
                    await self._backfill_month(client, sensor, year, month, ts_writer)
                except Exception:
                    logger.exception(
                        "%s %s: error backfilling %d-%02d",
                        self.name, sensor.device_id, year, month,
                    )
                month += 1
                if month > 12:
                    month = 1
                    year += 1
