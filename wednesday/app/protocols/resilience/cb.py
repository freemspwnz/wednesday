from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class CircuitBreaker(Protocol):
    """Протокол для circuit breaker."""

    def __call__(self, func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]: ...

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        **kwargs: object,
    ) -> T: ...

    async def open(self) -> None: ...
    async def half_open(self) -> None: ...
    async def close(self) -> None: ...
