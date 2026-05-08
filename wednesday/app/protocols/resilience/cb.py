from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class ICircuitBreaker(Protocol):
    """Протокол для circuit breaker."""

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T: ...
