from functools import cached_property

from prometheus_client import CollectorRegistry

from app.protocols import Logger, MetricsCollector, MetricsRegistry
from infra.config import Config
from infra.observe.loguru import get_logger, setup_logging
from infra.observe.prometheus import (
    PrometheusCollector,
    PrometheusRegistry,
)


class ObserveContainer:
    """Контейнер для создания observe-слоя."""

    def __init__(
        self,
        *,
        config: Config,
    ) -> None:
        self._config = config

    @cached_property
    def logger(self) -> Logger:
        secrets: list[str] = [
            self._config.postgres.password.get_secret_value(),
            self._config.redis.password.get_secret_value(),
        ]

        setup_logging(
            config=self._config.logging,
            env=self._config.env,
            version=self._config.version,
            secrets=secrets,
        )

        return get_logger()

    @cached_property
    def metrics_registry(self) -> MetricsRegistry:
        return PrometheusRegistry(
            collector=self.collector,
        )

    @cached_property
    def collector(self) -> MetricsCollector:
        return PrometheusCollector(
            registry=CollectorRegistry(),
            logger=self.logger,
            config=self._config.metrics,
            env=self._config.env,
            version=self._config.version,
        )
