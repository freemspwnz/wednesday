"""Исключения и маппинг для клиентов Сбербанка (Kandinsky, GigaChat).

Содержит функцию маппинга HTTP статусов в доменные исключения
и константы для HTTP статусов.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from shared.base.exceptions import APIError, AuthenticationError, ClientError, RateLimitError

if TYPE_CHECKING:
    from aiohttp import ClientResponse

HTTP_STATUS_UNAUTHORIZED: Final[int] = 401
HTTP_STATUS_FORBIDDEN: Final[int] = 403
HTTP_STATUS_TOO_MANY_REQUESTS: Final[int] = 429


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
