from builtins import BaseException
from collections.abc import Callable, Iterable

from app.protocols import CircuitBreaker, RateLimiter, Retrier
from infra.config import (
    CircuitBreakerConfig,
    Config,
    RateLimitConfig,
    RetryConfig,
)
from infra.resilience.asyncbreaker import cb_factory
from infra.resilience.limits import rl_factory
from infra.resilience.tenacity import Tenacity, is_retryable

from .observe import ObserveContainer
from .persistence import PersistenceContainer


class ResilienceContainer:
    """Контейнер для создания resilience-слоя."""

    def __init__(
        self,
        *,
        config: Config,
        observe: ObserveContainer,
        persistence: PersistenceContainer,
    ) -> None:
        self._config = config
        self._observe = observe
        self._persistence = persistence
        self._logger = self._observe.logger.bind(module=self.__class__.__name__)

    def retry(
        self,
        *,
        config: RetryConfig | None = None,
        predicate: Callable[[BaseException], bool] = is_retryable,
    ) -> Retrier:
        if config is None:
            config = self._config.retry

        return Tenacity(
            config=config,
            predicate=predicate,
            metrics=self._observe.metrics_registry.retry_metrics,
            logger=self._observe.logger,
        )

    def circuit_breaker(
        self,
        *,
        config: CircuitBreakerConfig | None = None,
        exclude: Iterable[type[BaseException]] = (),
    ) -> CircuitBreaker:
        if config is None:
            config = self._config.circuit_breaker

        return cb_factory(
            config=config,
            env=self._config.env,
            version=self._config.version,
            redis=self._persistence.redis,
            exclude=exclude,
            metrics=self._observe.metrics_registry.cb_metrics,
            logger=self._observe.logger,
        )

    def rate_limiter(
        self,
        *,
        config: RateLimitConfig | None = None,
    ) -> RateLimiter:
        if config is None:
            config = self._config.rate_limit

        return rl_factory(
            config=config,
            env=self._config.env,
            version=self._config.version,
            redis_dsn=self._config.redis.dsn,
            redis_pool=self._persistence.redis.connection_pool,
            metrics=self._observe.metrics_registry.rl_metrics,
            logger=self._observe.logger,
        )
