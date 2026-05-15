from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol, TypeVar, runtime_checkable

L = TypeVar("L")


@runtime_checkable
class RateLimiter[L](Protocol):
    """Rate limiter protocol."""

    @property
    def limits(self) -> Mapping[str, L]:
        """Get limits."""
        ...

    def __call__(
        self, limit: L, *args: str, cost: int = 1
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Rate limiter decorator."""
        ...

    async def call(self, limit: L, *args: str, cost: int = 1) -> None:
        """Execute request and increment counter by key."""
        ...

    async def test(self, limit: L, *args: str, cost: int = 1) -> None:
        """Execute test request without incrementing counter."""
        ...

    async def reset(self, limit: L, *args: str) -> None:
        """Reset counter by key."""
        ...

    async def get_window_stats(self, limit: L, *args: str) -> object:
        """Get window stats by request."""
        ...
