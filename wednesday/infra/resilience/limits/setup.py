from typing import Literal

from limits import RateLimitItem, parse
from limits.aio.storage import MemoryStorage, RedisStorage, Storage
from limits.aio.strategies import STRATEGIES
from redis.asyncio import ConnectionPool

from app.protocols import Logger, RateLimiter, RLMetrics
from infra.config.resilience.limits import RateLimitConfig

from .limiter import Limits

STRATEGY = Literal["fixed-window", "moving-window", "sliding-window-counter"]


def rl_factory(  # noqa: PLR0913, PLR0917
    config: RateLimitConfig,
    env: str,
    version: str,
    redis_dsn: str,
    redis_pool: ConnectionPool,
    metrics: RLMetrics,
    logger: Logger,
) -> RateLimiter:
    """Setup rate limiter factory."""
    logger.debug("Building rate limiter...")
    limits = _limits(config.name, config.limits)
    storage = _storage(config.storage, env, version, redis_dsn, redis_pool)
    limiter = STRATEGIES[config.strategy](storage=storage)

    rl = Limits(
        limiter=limiter,
        metrics=metrics,
        logger=logger,
    )
    rl.limits = limits
    return rl


def _limits(name: str, limits: dict[str, str]) -> dict[str, RateLimitItem]:
    """Parse limits from config."""
    result: dict[str, RateLimitItem] = {}
    for k, v in limits.items():
        item = parse(v)
        item.namespace = f"{name}:{k}"
        result[k] = item
    return result


def _storage(
    storage: Literal["redis", "memory"],
    env: str,
    version: str,
    redis_dsn: str,
    redis_pool: ConnectionPool,
) -> Storage:
    """Setup storage for rate limiter."""
    match storage:
        case "redis":
            return RedisStorage(
                uri=redis_dsn,
                wrap_exceptions=True,
                implementation="redispy",
                key_prefix=f"wednesday:{env}:{version}",
                connection_pool=redis_pool,
            )
        case "memory":
            return MemoryStorage(wrap_exceptions=True)
        case _:
            raise ValueError(f"Invalid storage: {storage}")
