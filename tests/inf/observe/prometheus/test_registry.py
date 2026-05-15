"""Тесты PrometheusRegistry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infra.observe.prometheus import PrometheusRegistry
from infra.observe.prometheus.adapters import (
    AsyncbreakerMetrics,
    LimitsMetrics,
    RedisMetrics,
    SQLAMetrics,
    TenacityMetrics,
)


@pytest.mark.unit
class TestPrometheusRegistry:
    def test_properties_return_singletons(self) -> None:
        mock_collector = MagicMock()
        reg = PrometheusRegistry(collector=mock_collector)

        assert isinstance(reg.retry_metrics, TenacityMetrics)
        assert isinstance(reg.cb_metrics, AsyncbreakerMetrics)
        assert isinstance(reg.cache_metrics, RedisMetrics)
        assert isinstance(reg.db_metrics, SQLAMetrics)
        assert isinstance(reg.rl_metrics, LimitsMetrics)

        assert reg.retry_metrics is reg.retry_metrics
        assert reg.cb_metrics is reg.cb_metrics

    def test_adapters_share_collector(self) -> None:
        mock_collector = MagicMock()
        reg = PrometheusRegistry(collector=mock_collector)
        assert reg.retry_metrics._collector is mock_collector
        assert reg.cb_metrics._collector is mock_collector
