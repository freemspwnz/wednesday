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
    """Container for creating resilience layer."""

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

    def retrier(
        self,
        *,
        config: RetryConfig,
        predicate: Callable[[BaseException], bool] = is_retryable,
    ) -> Retrier:
        return Tenacity(
            config=config,
            predicate=predicate,
            metrics=self._observe.metrics.retry,
            logger=self._observe.logger,
        )

    def breaker(
        self,
        *,
        config: CircuitBreakerConfig,
        exclude: Iterable[type[BaseException]] = (),
    ) -> CircuitBreaker:
        return cb_factory(
            config=config,
            env=self._config.env,
            version=self._config.version,
            redis=self._persistence.redis,
            exclude=exclude,
            metrics=self._observe.metrics.cb,
            logger=self._observe.logger,
        )

    def limiter(
        self,
        *,
        config: RateLimitConfig,
    ) -> RateLimiter:
        return rl_factory(
            config=config,
            env=self._config.env,
            version=self._config.version,
            redis_dsn=self._config.redis.dsn,
            redis_pool=self._persistence.redis.connection_pool,
            metrics=self._observe.metrics.rl,
            logger=self._observe.logger,
        )
