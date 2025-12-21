"""Исключения и маппинг для клиентов Сбербанка (Kandinsky, GigaChat).

Содержит:
- функцию маппинга HTTP статусов в доменные исключения;
- декоратор для автоматической обработки ошибок;
- функцию для определения необходимости retry;
- константы для HTTP статусов.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TYPE_CHECKING, Final, ParamSpec, TypeVar

from loguru import logger
from pydantic import ValidationError

from shared.base.exceptions import APIError, AuthenticationError, ClientError, NetworkError, RateLimitError

P = ParamSpec("P")

if TYPE_CHECKING:
    from aiohttp import ClientResponse

HTTP_STATUS_UNAUTHORIZED: Final[int] = 401
HTTP_STATUS_FORBIDDEN: Final[int] = 403
HTTP_STATUS_TOO_MANY_REQUESTS: Final[int] = 429

T = TypeVar("T")


def map_http_status_to_domain_exception(
    status_code: int,
    message: str | None = None,
    response_body: str | None = None,
    response: ClientResponse | None = None,
) -> ClientError:
    """Маппит HTTP статус код в доменное исключение.

    Args:
        status_code: HTTP статус код.
        message: Кастомное сообщение об ошибке (опционально).
        response_body: Тело ответа от API (опционально).
        response: Объект ответа aiohttp для извлечения дополнительной информации (опционально).

    Returns:
        Соответствующее доменное исключение.
    """
    if status_code == HTTP_STATUS_UNAUTHORIZED:
        default_message = "Неверный API ключ (401 Unauthorized)"
        return AuthenticationError(
            message or default_message,
            original_error=None,
        )
    elif status_code == HTTP_STATUS_FORBIDDEN:
        default_message = "Доступ запрещён (403 Forbidden)"
        return AuthenticationError(
            message or default_message,
            original_error=None,
        )
    elif status_code == HTTP_STATUS_TOO_MANY_REQUESTS:
        default_message = "Превышен лимит запросов (429 Too Many Requests)"
        return RateLimitError(
            message or default_message,
            original_error=None,
        )
    else:
        # Все остальные ошибки (4xx, 5xx)
        default_message = f"Ошибка API (HTTP {status_code})"
        return APIError(
            message or default_message,
            original_error=None,
        )


# Обратная совместимость: экспортируем функцию под старым именем
map_http_status_to_exception = map_http_status_to_domain_exception


def map_client_errors(
    event_name: str | None = None,
    service_name: str | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Декоратор для автоматической обработки ошибок клиентов.

    Автоматически:
    - Пробрасывает доменные исключения (AuthenticationError, RateLimitError, NetworkError, APIError)
    - Оборачивает ValidationError в APIError с логированием
    - Оборачивает неожиданные исключения в APIError с логированием

    Args:
        event_name: Имя события для логирования (опционально, по умолчанию используется имя функции).
        service_name: Имя сервиса для логирования (опционально).

    Returns:
        Декоратор для методов клиентов.

    Example:
        ```python
        @map_client_errors(event_name="kandinsky_generate", service_name="kandinsky")
        async def generate(self, prompt: str, user_id: str | None = None) -> bytes:
            # основная логика без обработки ошибок
            ...
        ```
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # Определяем имя события и сервиса
            event = event_name or func.__name__
            service = service_name or "client"

            # Пытаемся получить user_id из kwargs для логирования
            user_id = kwargs.get("user_id")
            bound = logger.bind(event=event, user_id=user_id)

            try:
                return await func(*args, **kwargs)
            except (AuthenticationError, RateLimitError, NetworkError, APIError):
                # Пробрасываем доменные исключения как есть
                raise
            except ValidationError as e:
                # Оборачиваем ValidationError в APIError
                bound.bind(
                    error=str(e),
                ).error(f"Ошибка валидации ответа {service} API: {e}")
                raise APIError(
                    f"Ошибка валидации ответа {service} API: {e}",
                    original_error=e,
                ) from e
            except Exception as exc:
                # Оборачиваем неожиданные исключения в APIError
                bound.bind(error=str(exc)).error(
                    f"Неожиданная ошибка в {service}: {exc}",
                )
                raise APIError(
                    f"Неожиданная ошибка в {service}: {exc}",
                    original_error=exc,
                ) from exc

        return wrapper

    return decorator


def should_retry(exc: ClientError) -> bool:
    """Определяет, можно ли повторить запрос при данной ошибке.

    Args:
        exc: Исключение клиента.

    Returns:
        True если можно retry, False иначе.
    """
    # Сетевые ошибки можно retry
    if isinstance(exc, NetworkError):
        return True

    # Rate limit можно retry после задержки
    if isinstance(exc, RateLimitError):
        return True

    # Ошибки аутентификации и другие API ошибки не стоит retry
    return False
