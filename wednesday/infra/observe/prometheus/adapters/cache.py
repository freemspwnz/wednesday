"""Redis cache metrics adapter."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.protocols import CacheMetrics, CacheOperation, MetricsCollector

_PREFIX = "redis"


class RedisMetrics(CacheMetrics):
    """Адаптер метрик для Redis-кэша."""

    def __init__(self, *, collector: MetricsCollector) -> None:
        self._collector = collector

    @asynccontextmanager
    async def track(self, operation: str) -> AsyncIterator[CacheOperation]:
        start = time.perf_counter()
        res = CacheOperation()
        errored = False
        try:
            yield res
        except Exception:
            errored = True
            raise
        finally:
            duration = time.perf_counter() - start
            status = self._resolve_status(res=res, errored=errored)
            self._collector.increment(
                name=f"{_PREFIX}_operations_total",
                labels={"operation": operation, "status": status},
            )
            self._collector.observe(
                name=f"{_PREFIX}_operation_duration_seconds",
                value=duration,
                labels={"operation": operation},
            )

    def set_queue_size(self, queue_name: str, count: int) -> None:
        self._collector.set_gauge(
            name=f"{_PREFIX}_queue_size",
            value=float(count),
            labels={"queue": queue_name},
        )

    @staticmethod
    def _resolve_status(*, res: CacheOperation, errored: bool) -> str:
        if errored:
            return "error"
        if res.hit is True:
            return "hit"
        if res.hit is False:
            return "miss"
        return "success"
