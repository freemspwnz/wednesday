from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple, Protocol, runtime_checkable


@runtime_checkable
class IRateLimiter(Protocol):
    """Протокол для сервиса rate limiting."""

    @property
    def limits(self) -> dict[str, Any]: ...

    def __call__(self, limit: object, *args: str, cost: int) -> Callable[..., Awaitable[Any]]: ...

    async def call(self, limit: object, *args: str, cost: int) -> None:
        """Выполняет запрос и инкрементирует счётчик по ключу."""
        ...

    async def test(self, limit: object, *args: str, cost: int) -> None:
        """Выполняет тестовый запрос без инкрементации счётчика."""
        ...

    async def get_window_stats(self, limit: object, *args: str) -> NamedTuple | None:
        """Возвращает статистику по запросу."""
        ...

    async def reset(self, limit: object, *args: str) -> None:
        """Сбрасывает счётчик по ключу."""
        ...
