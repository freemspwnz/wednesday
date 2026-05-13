import asyncio

from redis.asyncio import Redis
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    TimeoutError as RedisTimeoutError,
)

from app.protocols import Logger
from infra.config import RedisConfig

_REDIS_CLOSE_TIMEOUT = 2.0


def build_redis(
    *,
    config: RedisConfig,
    logger: Logger,
) -> Redis:
    logger.debug("Building Redis...")
    redis = Redis.from_url(
        url=config.dsn,
        decode_responses=config.decode_responses,
        max_connections=config.max_connections,
        socket_timeout=config.socket_timeout,
    )
    logger.debug("Redis built")
    return redis


async def close_redis(
    *,
    redis: Redis,
    logger: Logger,
) -> None:
    try:
        async with asyncio.timeout(_REDIS_CLOSE_TIMEOUT):
            await redis.aclose()
        logger.info("Redis connection pool closed successfully.")
    except TimeoutError:
        logger.warning("Redis connection pool close timed out. Forced exit.")
    except (RedisConnectionError, RedisTimeoutError):
        logger.warning("Redis connection is already closed or lost.")
    except Exception:
        logger.warning("Non-critical error while closing Redis", exc_info=True)
