"""Helper-функции для обработки ошибок клиентов."""

from __future__ import annotations

from loguru import logger

from infra.clients.exceptions import ClientError, NetworkError, RateLimitError


def log_client_error(exc: ClientError, context: str = "") -> None:
    """Логирует ошибку клиента с контекстом.

    Args:
        exc: Исключение клиента.
        context: Дополнительный контекст (метод, параметры и т.д.).
    """
    context_msg = f" ({context})" if context else ""
    logger.error(f"Ошибка клиента{context_msg}: {exc}")
    if exc.original_error:
        logger.debug(f"Исходная ошибка: {exc.original_error}")


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
