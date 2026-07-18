"""Fixtures for ``tests/inf/persistence/redis_py/``."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from app.protocols import CacheMetrics, CacheOperation


@pytest.fixture
def cache_metrics() -> MagicMock:
    """Minimal ``CacheMetrics`` stand-in for ``RedisClient`` tests."""

    @asynccontextmanager
    async def track(_operation: str) -> AsyncIterator[CacheOperation]:
        yield CacheOperation()

    m = MagicMock(spec=CacheMetrics)
    m.track = track
    m.set_queue_size = MagicMock()
    return m
