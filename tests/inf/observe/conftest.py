"""Фикстуры для ``tests/infra/observe/`` (prometheus и др.)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from prometheus_client import CollectorRegistry

from infra.config.observe import MetricsConfig
from infra.observe.prometheus import PrometheusCollector


@pytest.fixture
def metrics_config() -> MetricsConfig:
    return MetricsConfig(enabled=False, host="127.0.0.1", port=0)


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
