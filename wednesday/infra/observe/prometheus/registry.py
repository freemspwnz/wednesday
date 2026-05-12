"""Prometheus registry — фасад над per-typed адаптерами."""

from functools import cached_property

from app.protocols import MetricsCollector, MetricsRegistry

from .adapters import (
    AsyncbreakerMetrics,
    LimitsMetrics,
    RedisMetrics,
    SQLAMetrics,
    TenacityMetrics,
)


class PrometheusRegistry(MetricsRegistry):
    """Регистр инфраструктурных адаптеров метрик."""

    def __init__(self, *, collector: MetricsCollector) -> None:
        self._collector = collector

    @cached_property
    def retry_metrics(self) -> TenacityMetrics:
        return TenacityMetrics(collector=self._collector)

    @cached_property
    def cb_metrics(self) -> AsyncbreakerMetrics:
        return AsyncbreakerMetrics(collector=self._collector)

    @cached_property
    def cache_metrics(self) -> RedisMetrics:
        return RedisMetrics(collector=self._collector)

    @cached_property
    def db_metrics(self) -> SQLAMetrics:
        return SQLAMetrics(collector=self._collector)

    @cached_property
    def rl_metrics(self) -> LimitsMetrics:
        return LimitsMetrics(collector=self._collector)
