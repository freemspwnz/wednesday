from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RateLimiter(Protocol):
    """Rate limiter protocol."""

    @property
    def limits(self) -> dict[str, object]:
        """Get limits."""
        ...

    def __call__(
        self, limit: object, *args: str, cost: int = 1
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
        """Rate limiter decorator."""
        ...

    async def call(self, limit: object, *args: str, cost: int = 1) -> None:
        """Execute request and increment counter by key."""
        ...

    async def test(self, limit: object, *args: str, cost: int = 1) -> None:
        """Execute test request without incrementing counter."""
        ...

    async def reset(self, limit: object, *args: str) -> None:
        """Reset counter by key."""
        ...

    async def get_window_stats(self, limit: object, *args: str) -> object:
        """Get window stats by request."""
        ...
