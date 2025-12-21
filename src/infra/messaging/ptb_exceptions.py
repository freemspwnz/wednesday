"""Декоратор для маппинга telegram.error в доменные исключения."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from telegram.error import NetworkError, TelegramError, TimedOut

from shared.base.exceptions import MessagingAPIError, MessagingNetworkError

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def map_telegram_exceptions(func: F) -> F:
    """Декоратор для маппинга telegram.error в доменные исключения.

    Args:
        func: Асинхронная функция, которая может выбрасывать telegram.error.

    Returns:
        Обёрнутая функция, которая выбрасывает доменные исключения.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        try:
            return await func(*args, **kwargs)
        except (NetworkError, TimedOut) as e:
            # Сетевые ошибки и таймауты
            raise MessagingNetworkError(str(e)) from e
        except TelegramError as e:
            # Остальные ошибки Telegram API
            raise MessagingAPIError(str(e)) from e

    return wrapper  # type: ignore[return-value]
