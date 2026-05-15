import time
from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from math import ceil
from typing import TypeVar

from limits import RateLimitItem, WindowStats
from limits.aio.strategies import RateLimiter as Limiter
from limits.errors import ConcurrentUpdateError, StorageError

from app.exceptions import LimitStorageError, TooManyRequests, UnexpectedLimitError
from app.protocols import Logger, RateLimiter, RLMetrics

T = TypeVar("T")

_DEFAULT_RETRY_AFTER = 1


class Limits(RateLimiter[RateLimitItem]):
    """Rate limiter based on limits library."""

    def __init__(
        self,
        *,
        limiter: Limiter,
        metrics: RLMetrics,
        logger: Logger,
    ) -> None:
        self._limits: Mapping[str, RateLimitItem] = {}
        self._limiter = limiter
        self._metrics = metrics
        self._logger = logger.bind(module=self.__class__.__name__)

    def __call__(
        self,
        limit: RateLimitItem,
        *identifiers: str,
        cost: int = 1,
    ) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
        def decorator(
            func: Callable[..., Awaitable[T]],
        ) -> Callable[..., Awaitable[T]]:
            @wraps(func)
            async def wrapper(*args: object, **kwargs: object) -> T:
                await self.call(limit, *identifiers, cost=cost)
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    @property
    def limits(self) -> Mapping[str, RateLimitItem]:
        return self._limits

    @limits.setter
    def limits(self, limits: Mapping[str, RateLimitItem]) -> None:
        self._limits = limits

    async def call(
        self,
        limit: RateLimitItem,
        *identifiers: str,
        cost: int = 1,
    ) -> None:
        self._logger.debug(f"Rate limiter {limit.namespace} call request")
        await self._run_op(self._limiter.hit, limit, *identifiers, cost=cost)

    async def test(
        self,
        limit: RateLimitItem,
        *identifiers: str,
        cost: int = 1,
    ) -> None:
        self._logger.debug(f"Rate limiter {limit.namespace} test call request")
        await self._run_op(self._limiter.test, limit, *identifiers, cost=cost)

    async def get_window_stats(
        self,
        limit: RateLimitItem,
        *identifiers: str,
    ) -> WindowStats:
        self._logger.debug(f"Rate limit {limit.namespace} window stats request")
        self._metrics.before_call()

        try:
            stats = await self._limiter.get_window_stats(limit, *identifiers)

        except (ConcurrentUpdateError, StorageError) as e:
            self._logger.warning(
                "Rate limiter storage error",
                operation="get_window_stats",
                limiter=limit.namespace,
            )
            raise LimitStorageError("Rate limiter backend unavailable") from e

        except Exception as e:
            self._logger.exception(
                "Rate limiter get_window_stats failed",
                operation="get_window_stats",
                limiter=limit.namespace,
            )
            raise UnexpectedLimitError(
                f"Unexpected error while getting window stats for rate limiter {limit.namespace}"
            ) from e

        self._metrics.on_get_stats(
            name=limit.namespace,
            reset_time=stats.reset_time,
            remaining=stats.remaining,
        )

        return stats

    async def reset(
        self,
        limit: RateLimitItem,
        *identifiers: str,
    ) -> None:
        self._logger.debug(f"Rate limiter {limit.namespace} reset request")
        self._metrics.before_call()

        try:
            await self._limiter.clear(limit, *identifiers)

        except (ConcurrentUpdateError, StorageError) as e:
            self._logger.warning(
                "Rate limiter storage error",
                operation="reset",
                limiter=limit.namespace,
            )
            raise LimitStorageError("Rate limiter backend unavailable") from e

        except Exception as e:
            self._logger.exception(
                "Rate limiter reset failed",
                operation="reset",
                limiter=limit.namespace,
            )
            raise UnexpectedLimitError(f"Unexpected error while resetting rate limiter {limit.namespace}") from e

        self._metrics.on_reset(name=limit.namespace, limit=limit.amount)

    async def _run_op(
        self,
        op: Callable[..., Awaitable[bool]],
        limit: RateLimitItem,
        *identifiers: str,
        cost: int = 1,
    ) -> None:
        self._metrics.before_call()

        result = None
        try:
            result = await op(limit, *identifiers, cost=cost)

        except (ConcurrentUpdateError, StorageError) as e:
            self._logger.warning(
                "Rate limiter storage error",
                operation=op.__name__,
                limiter=limit.namespace,
            )
            raise LimitStorageError("Rate limiter backend unavailable") from e

        except Exception as e:
            self._logger.exception(
                "Rate limiter unexpected error",
                operation=op.__name__,
                limiter=limit.namespace,
            )
            raise UnexpectedLimitError(f"Unexpected error while calling rate limiter {limit.namespace}") from e

        self._metrics.on_call(
            name=limit.namespace,
            limit=str(limit),
            result=result,
        )

        if result is False:
            try:
                stats = await self.get_window_stats(limit, *identifiers)
            except LimitStorageError:
                stats = None
            raise self._build_exception(limit, stats)

    @staticmethod
    def _build_exception(limit: RateLimitItem, stats: WindowStats | None = None) -> TooManyRequests:
        sleep_time = _DEFAULT_RETRY_AFTER
        reset_time = time.time() + sleep_time
        remaining = None

        if stats is not None:
            sleep_time = max(0, ceil(stats.reset_time - time.time()))
            reset_time = stats.reset_time
            remaining = stats.remaining

        return TooManyRequests(
            message="Rate limit exceeded. Too many requests.",
            retry_after=sleep_time,
            reset_at=reset_time,
            remaining=remaining,
            limit=limit.namespace,
        )
