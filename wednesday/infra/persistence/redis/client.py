"""Async Redis client implementing the application cache protocol."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import NoReturn, TypeVar

import redis.exceptions as redis_exc
from redis.asyncio import Redis

from app.exceptions import CacheTimeoutError, CacheUnavailableError, UnexpectedCacheError
from app.protocols import CacheClient, CacheMetrics, Logger

R = TypeVar("R")


class RedisClient(CacheClient):
    """Redis-backed ``CacheClient`` with optional queue-length metrics.

    Wraps ``redis.asyncio.Redis`` and records cache operation metrics.
    Network and server errors of Redis are translated to ``app.exceptions`` and
    propagated to the calling code (use case / middleware solve retries).
    ``get_queue_size`` — infra helper outside the ``CacheClient`` protocol.
    """

    def __init__(
        self,
        *,
        redis: Redis,
        metrics: CacheMetrics,
        logger: Logger,
    ) -> None:
        self._redis = redis
        self._metrics = metrics
        self._log = logger.bind(module=self.__class__.__name__)

    async def get(self, key: str) -> bytes | str | None:
        """Return the raw value for ``key`` (``str``, ``bytes``, or ``None`` depending on client settings)."""
        async with self._metrics.track("get") as op:
            result = await self._execute("get", lambda: self._redis.get(key))
            op.hit = result is not None
            return result  # type: ignore[no-any-return]

    async def set(self, key: str, value: str | bytes | int | float, expire: int | timedelta | None = None) -> None:
        """Set ``key`` to ``value`` with optional TTL (seconds or ``timedelta``)."""
        async with self._metrics.track("set"):
            await self._execute("set", lambda: self._redis.set(key, value, ex=expire))

    async def delete(self, key: str) -> None:
        """Delete ``key`` if it exists."""
        async with self._metrics.track("delete"):
            await self._execute("delete", lambda: self._redis.delete(key))

    async def exists(self, key: str) -> bool:
        """Return whether ``key`` exists."""
        async with self._metrics.track("exists") as op:
            result = await self._execute("exists", lambda: self._redis.exists(key))
            op.hit = bool(result)
            return op.hit

    async def get_queue_size(self, queue_name: str) -> int:
        """Return list length at ``queue_name`` and publish it as a gauge (infra helper)."""
        async with self._metrics.track("llen"):
            count = await self._execute("llen", lambda: self._redis.llen(queue_name))  # type: ignore[arg-type, return-value]
            self._metrics.set_queue_size(queue_name, count)
            return count

    async def _execute(self, operation: str, coro: Callable[[], Awaitable[R]]) -> R:
        try:
            return await coro()
        except redis_exc.RedisError as e:
            self._map_redis_error(operation, e)

    def _map_redis_error(self, operation: str, exc: redis_exc.RedisError) -> NoReturn:
        """Логирует сбой Redis и поднимает соответствующее исключение application-слоя."""
        if isinstance(exc, redis_exc.TimeoutError):
            self._log.warning(
                "Redis operation timed out",
                operation=operation,
                exc_info=exc,
            )
            raise CacheTimeoutError(
                f"Redis operation timed out: {operation}",
                operation=operation,
            ) from exc
        if isinstance(
            exc,
            redis_exc.ConnectionError | redis_exc.BusyLoadingError | redis_exc.TryAgainError,
        ):
            self._log.warning(
                "Redis temporarily unavailable",
                operation=operation,
                exc_info=exc,
            )
            raise CacheUnavailableError(
                f"Redis unavailable: {operation}",
                operation=operation,
            ) from exc
        self._log.warning(
            "Unexpected Redis error",
            operation=operation,
            exc_info=exc,
        )
        raise UnexpectedCacheError(
            f"Unexpected Redis failure during {operation}",
        ) from exc
