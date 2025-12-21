"""Исключения для HTTP-клиентов."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from aiohttp import ClientResponse

HTTP_STATUS_UNAUTHORIZED: Final[int] = 401
HTTP_STATUS_FORBIDDEN: Final[int] = 403
HTTP_STATUS_TOO_MANY_REQUESTS: Final[int] = 429


class ClientError(Exception):
    """Базовое исключение для всех ошибок клиентов."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        """Инициализирует исключение клиента.

        Args:
            message: Сообщение об ошибке.
            original_error: Исходное исключение, которое привело к этой ошибке (опционально).
        """
        super().__init__(message)
        self.message = message
        self.original_error = original_error


class AuthenticationError(ClientError):
    """Ошибка аутентификации (401 Unauthorized, 403 Forbidden)."""

    def __init__(
        self,
        message: str,
        status_code: int,
        response_body: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """Инициализирует ошибку аутентификации.

        Args:
            message: Сообщение об ошибке.
            status_code: HTTP статус код (401 или 403).
            response_body: Тело ответа от API (опционально).
            original_error: Исходное исключение (опционально).
        """
        super().__init__(message, original_error)
        self.status_code = status_code
        self.response_body = response_body


class RateLimitError(ClientError):
    """Превышен лимит запросов (429 Too Many Requests)."""

    def __init__(
        self,
        message: str,
        status_code: int = 429,
        response_body: str | None = None,
        retry_after: int | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """Инициализирует ошибку превышения лимита запросов.

        Args:
            message: Сообщение об ошибке.
            status_code: HTTP статус код (обычно 429).
            response_body: Тело ответа от API (опционально).
            retry_after: Время в секундах до следующей попытки (из заголовка Retry-After, опционально).
            original_error: Исходное исключение (опционально).
        """
        super().__init__(message, original_error)
        self.status_code = status_code
        self.response_body = response_body
        self.retry_after = retry_after


class NetworkError(ClientError):
    """Сетевая ошибка (таймаут, ошибка соединения, DNS и т.д.)."""

    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
    ) -> None:
        """Инициализирует сетевую ошибку.

        Args:
            message: Сообщение об ошибке.
            original_error: Исходное исключение (aiohttp.ClientConnectorError, TimeoutError и т.д.).
        """
        super().__init__(message, original_error)


class APIError(ClientError):
    """Ошибка API (другие HTTP статусы: 4xx, 5xx)."""

    def __init__(
        self,
        message: str,
        status_code: int,
        response_body: str | None = None,
        original_error: Exception | None = None,
    ) -> None:
        """Инициализирует ошибку API.

        Args:
            message: Сообщение об ошибке.
            status_code: HTTP статус код.
            response_body: Тело ответа от API (опционально).
            original_error: Исходное исключение (опционально).
        """
        super().__init__(message, original_error)
        self.status_code = status_code
        self.response_body = response_body


def map_http_status_to_exception(
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
            status_code=HTTP_STATUS_UNAUTHORIZED,
            response_body=response_body,
        )
    elif status_code == HTTP_STATUS_FORBIDDEN:
        default_message = "Доступ запрещён (403 Forbidden)"
        return AuthenticationError(
            message or default_message,
            status_code=HTTP_STATUS_FORBIDDEN,
            response_body=response_body,
        )
    elif status_code == HTTP_STATUS_TOO_MANY_REQUESTS:
        retry_after = None
        if response is not None:
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header:
                try:
                    retry_after = int(retry_after_header)
                except (ValueError, TypeError):
                    pass

        default_message = "Превышен лимит запросов (429 Too Many Requests)"
        return RateLimitError(
            message or default_message,
            status_code=HTTP_STATUS_TOO_MANY_REQUESTS,
            response_body=response_body,
            retry_after=retry_after,
        )
    else:
        # Все остальные ошибки (4xx, 5xx)
        default_message = f"Ошибка API (HTTP {status_code})"
        return APIError(
            message or default_message,
            status_code=status_code,
            response_body=response_body,
        )
