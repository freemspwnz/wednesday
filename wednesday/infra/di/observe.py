from functools import cached_property

from app.protocols import Logger, MetricsRegistry
from infra.config import Config
from infra.observe.loguru import get_logger
from infra.observe.prometheus import PrometheusRegistry


class ObserveContainer:
    """Container for creating observe layer."""

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
            self._config.telegram.token.get_secret_value(),
            self._config.gigachat.auth_key.get_secret_value(),
        ]

        return get_logger(
            config=self._config.logging,
            env=self._config.env,
            version=self._config.version,
            secrets=secrets,
        )

    @cached_property
    def metrics(self) -> MetricsRegistry:
        return PrometheusRegistry(
            config=self._config.metrics,
            env=self._config.env,
            version=self._config.version,
            logger=self.logger,
        )
