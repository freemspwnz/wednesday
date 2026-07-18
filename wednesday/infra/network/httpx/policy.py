from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TypeVar

from app.protocols import CircuitBreaker, RateLimiter, Retrier

T = TypeVar("T")


class ResiliencePolicy:
    """
    Composes three protection layers for outbound HTTP calls.

    Application order (outer → inner):
      1. Retrier — retries transient failures.
      2. Circuit breaker — tracks failures on each attempt inside the retry loop.
      3. Rate limiter — throttles before the actual HTTP call.
      4. HTTP call.
    """

    _LIMIT_KEY = "base"

    def __init__(
        self,
        *,
        retrier: Retrier,
        breaker: CircuitBreaker,
        limiter: RateLimiter,
    ) -> None:
        self._retrier = retrier
        self._breaker = breaker
        self._limiter = limiter
        self._limit = self._limiter.limits[self._LIMIT_KEY]

    def __call__(
        self,
        func: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[T]]:
        """Return a wrapper that routes calls through all policy layers."""

        @wraps(func)
        async def wrapper(
            *args: object,
            **kwargs: object,
        ) -> T:
            return await self.apply(
                func,
                *args,
                **kwargs,
            )

        return wrapper

    async def apply(
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T:
        """Run ``func`` through retrier, circuit breaker, and rate limiter."""

        protected = self._retrier(self._breaker(self._limiter(self._limit)(func)))
        return await protected(*args, **kwargs)
