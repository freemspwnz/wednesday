"""Фикстуры для тестов infra (observe, persistence и т.д.)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from loguru import logger
from prometheus_client import CollectorRegistry

from app.protocols import CacheMetrics, CacheOperation
from infra.config.observe import MetricsConfig
from infra.observe.prometheus import PrometheusCollector


@pytest.fixture(autouse=True)
def isolate_loguru() -> Iterator[None]:
    logger.remove()
    yield
    logger.remove()


@pytest.fixture
def metrics_config() -> MetricsConfig:
    return MetricsConfig(enabled=False, host="127.0.0.1", port=0)


@pytest.fixture
def mock_logger() -> MagicMock:
    log = MagicMock()
    log.bind.return_value = log
    return log


@pytest.fixture
def registry() -> CollectorRegistry:
    return CollectorRegistry()


@pytest.fixture
def collector(
    metrics_config: MetricsConfig,
    registry: CollectorRegistry,
    mock_logger: MagicMock,
) -> PrometheusCollector:
    return PrometheusCollector(
        config=metrics_config,
        env="TEST",
        version="0.0.1",
        registry=registry,
        logger=mock_logger,
    )


@pytest.fixture
def cache_metrics() -> MagicMock:
    """Минимальная реализация ``CacheMetrics`` для тестов persistence (Redis и др.)."""

    @asynccontextmanager
    async def track(_operation: str) -> AsyncIterator[CacheOperation]:
        yield CacheOperation()

    m = MagicMock(spec=CacheMetrics)
    m.track = track
    m.set_queue_size = MagicMock()
    return m
