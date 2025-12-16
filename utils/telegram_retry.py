from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TypeVar

import httpx
from telegram.error import NetworkError, TelegramError, TimedOut

T = TypeVar("T")

# Константа для дефолтного значения retry_after при 429 ошибке
RETRY_AFTER_DEFAULT_SECONDS = 60


async def retry_on_connect_error(
    func: Callable[..., Awaitable[T]],
    *args: object,
    max_retries: int = 3,
    delay: float = 2.0,
    handle_rate_limit: bool = True,
    **kwargs: object,
) -> T:
    """Выполняет функцию с повторными попытками при сетевых/Telgram-ошибках.

    Повторяются только ошибки, связанные с подключением/тайм-аутами HTTP-клиента
    и Telegram API. Остальные исключения пробрасываются без ретраев.

    Args:
        func: Асинхронная функция для выполнения.
        *args: Позиционные аргументы для функции.
        max_retries: Максимальное количество попыток.
        delay: Базовая задержка между попытками (в секундах).
        handle_rate_limit: Если True, обрабатывает TelegramError с кодом 429 (rate limit),
            используя retry_after из ошибки или заголовков ответа.
        **kwargs: Именованные аргументы для функции.

    Returns:
        Результат выполнения функции.

    Raises:
        Последнее исключение, если все попытки исчерпаны.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except TelegramError as e:
            # Обработка rate limit (429)
            if handle_rate_limit:
                error_str = str(e).lower()
                is_429 = "429" in error_str or "rate limit" in error_str or "too many requests" in error_str

                if is_429 and attempt < max_retries:
                    # Читаем retry_after из атрибута ошибки или заголовков ответа
                    retry_after = RETRY_AFTER_DEFAULT_SECONDS
                    if hasattr(e, "retry_after") and e.retry_after:
                        retry_after = int(e.retry_after)
                    elif hasattr(e, "response") and e.response:
                        retry_after_header = e.response.headers.get("retry-after")
                        if retry_after_header:
                            retry_after = int(retry_after_header)

                    await asyncio.sleep(retry_after)
                    continue

            # Для других TelegramError пробрасываем без ретраев
            raise
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
    handle_rate_limit: bool = True,
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
                handle_rate_limit=handle_rate_limit,
                **kwargs,
            )

        return wrapper

    return decorator
