from collections.abc import Callable, Iterable
from typing import Literal

from asyncbreaker import (
    CircuitBreaker as Breaker,
    CircuitBreakerStorage,
    CircuitMemoryStorage,
    CircuitRedisStorage,
)
from redis.asyncio import Redis

from app.protocols import CBMetrics, CircuitBreaker, Logger
from infra.config import CircuitBreakerConfig

from .breaker import Asyncbreaker
from .listeners import LoggingListener, MetricsListener


def cb_factory(  # noqa: PLR0913, PLR0917
    config: CircuitBreakerConfig,
    env: str,
    version: str,
    redis: Redis,
    exclude: Iterable[type[Exception] | Callable[[Exception], object]],
    metrics: CBMetrics,
    logger: Logger,
) -> CircuitBreaker:
    logger.debug("Building circuit breaker...")
    listeners = [
        MetricsListener(metrics),
        LoggingListener(logger),
    ]
    storage = _storage(
        storage=config.storage,
        namespace=f"wednesday:{env}:{version}:cb:{config.name}",
        redis=redis,
    )
    breaker = Breaker(
        fail_max=config.threshold,
        timeout_duration=config.cooldown,
        exclude=exclude,
        listeners=listeners,
        state_storage=storage,
        name=config.name,
    )
    return Asyncbreaker(
        breaker=breaker,
        logger=logger,
    )


def _storage(
    storage: Literal["redis", "memory"],
    namespace: str,
    redis: Redis,
) -> CircuitBreakerStorage:
    match storage:
        case "redis":
            return CircuitRedisStorage(
                redis_client=redis,
                namespace=namespace,
            )
        case "memory":
            return CircuitMemoryStorage()
        case _:
            raise ValueError(f"Invalid storage: {storage}")
