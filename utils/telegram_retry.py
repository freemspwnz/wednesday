from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TypeVar

import httpx
from telegram.error import NetworkError, TimedOut

T = TypeVar("T")


async def retry_on_connect_error(
    func: Callable[..., Awaitable[T]],
    *args: object,
    max_retries: int = 3,
    delay: float = 2.0,
    **kwargs: object,
) -> T:
    """Выполняет функцию с повторными попытками при сетевых/Telgram-ошибках.

    Повторяются только ошибки, связанные с подключением/тайм-аутами HTTP-клиента
    и Telegram API. Остальные исключения пробрасываются без ретраев.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            NetworkError,
            TimedOut,
        ) as e:
            last_error = e
            if attempt < max_retries:
                wait_time = delay * attempt
                await asyncio.sleep(wait_time)
            else:
                raise

    assert last_error is not None
    raise last_error


def retry_on_telegram_error(
    max_retries: int = 3,
    delay: float = 2.0,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Декоратор для типичных retry-паттернов вокруг Telegram-хелперов.

    Используется для обёртки методов, которые делают один или несколько вызовов
    Telegram API (send_message, send_photo и т.п.).
    """

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> T:
            return await retry_on_connect_error(
                func,
                *args,
                max_retries=max_retries,
                delay=delay,
                **kwargs,
            )

        return wrapper

    return decorator
