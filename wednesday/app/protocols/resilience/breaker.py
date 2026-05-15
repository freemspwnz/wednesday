from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class CircuitBreaker(Protocol):
    """Cicruit breaker protocol."""

    def __call__(self, func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        """Circuit breaker decorator."""
        ...

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T:
        """Execute function with circuit breaker."""
        ...

    async def open(self) -> None:
        """Open circuit breaker."""
        ...

    async def half_open(self) -> None:
        """Half open circuit breaker."""
        ...

    async def close(self) -> None:
        """Close circuit breaker."""
        ...
