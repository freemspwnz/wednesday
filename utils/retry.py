"""
Модуль для настройки retry-механик с экспоненциальным backoff и таймаутами.

Использует библиотеку tenacity для реализации retry-логики с:
- экспоненциальным backoff;
- логированием каждой попытки;
- метриками Prometheus;
- исключением определённых HTTP-статусов из retry;
- разными стратегиями для разных типов операций.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

import aiohttp
from tenacity import (
    retry,
    retry_base,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

if TYPE_CHECKING:
    from tenacity import RetryCallState

from utils.config import config
from utils.logger import get_logger, log_event

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])

# Логгер для tenacity
_tenacity_logger = get_logger(__name__)

# HTTP-статусы, для которых не нужно делать retry
_NO_RETRY_STATUS_CODES = {400, 401, 403}


def _should_retry_http_error(exception: BaseException) -> bool:
    """Проверяет, нужно ли делать retry для HTTP-ошибки.

    Не делаем retry для:
    - 400 (Bad Request) - ошибка клиента
    - 401 (Unauthorized) - проблемы с авторизацией
    - 403 (Forbidden) - нет доступа

    Args:
        exception: Исключение для проверки (может быть aiohttp.ClientResponseError
            или другим типом с атрибутом status).

    Returns:
        True если нужно делать retry, False иначе.
    """
    # Проверяем aiohttp.ClientResponseError
    if isinstance(exception, aiohttp.ClientResponseError):
        if exception.status in _NO_RETRY_STATUS_CODES:
            return False

    # Проверяем другие типы HTTP-ошибок
    if hasattr(exception, "status"):
        status = getattr(exception, "status", None)
        if status in _NO_RETRY_STATUS_CODES:
            return False

    return True


class _RetryIfNetworkError(retry_base):
    """
    Кастомное условие retry для сетевых ошибок.

    Проверяет тип исключения и HTTP-статус, исключая определённые коды ошибок.
    """

    def __call__(self, retry_state: RetryCallState) -> bool:
        """Проверяет, является ли исключение сетевой ошибкой, для которой нужен retry.

        Args:
            retry_state: Состояние retry от tenacity с информацией о попытке и исключении.

        Returns:
            True если нужно делать retry, False иначе.
        """
        if not retry_state.outcome or not retry_state.outcome.failed:
            return False

        exception = retry_state.outcome.exception()
        if not exception:
            return False

        # Проверяем типы исключений, для которых нужен retry
        is_retryable_exception = isinstance(
            exception,
            aiohttp.ClientConnectorError | aiohttp.ServerTimeoutError | TimeoutError | aiohttp.ClientError,
        )

        if not is_retryable_exception:
            return False

        # Для HTTP-ошибок дополнительно проверяем статус
        # (не делаем retry для 400, 401, 403)
        if not _should_retry_http_error(exception):
            return False

        return True


def _create_retry_decorator(  # noqa: PLR0913, PLR0917
    max_attempts: int,
    multiplier: float,
    min_wait: float,
    max_wait: float,
    service_name: str,
    method_name: str | None = None,
) -> Callable[[F], F]:
    """
    Создаёт декоратор retry с настройками логирования и метрик.

    Args:
        max_attempts: Максимальное количество попыток
        multiplier: Множитель для экспоненциального backoff
        min_wait: Минимальное время ожидания в секундах
        max_wait: Максимальное время ожидания в секундах
        service_name: Имя сервиса для логирования и метрик (например, "kandinsky", "gigachat")
        method_name: Имя метода для логирования (опционально)

    Returns:
        Декоратор retry
    """
    # Условие retry: только для сетевых ошибок и таймаутов, исключая определённые HTTP-статусы
    # Используем комбинацию retry_if_exception_type и кастомного класса для проверки HTTP-статусов
    retry_condition = (
        retry_if_exception_type((
            aiohttp.ClientConnectorError,
            aiohttp.ServerTimeoutError,
            TimeoutError,
            aiohttp.ClientError,
        ))
        & _RetryIfNetworkError()
    )

    def before_sleep_callback(retry_state: RetryCallState) -> None:
        """Логирует каждую попытку retry."""
        attempt = retry_state.attempt_number
        exception = retry_state.outcome.exception() if retry_state.outcome else None

        # Получаем время ожидания из next_action или вычисляем из настроек
        wait_time = 0.0
        if retry_state.next_action and hasattr(retry_state.next_action, "sleep"):
            wait_time = retry_state.next_action.sleep
        elif hasattr(retry_state, "wait"):
            # Fallback: вычисляем ожидаемое время из настроек экспоненциального backoff
            wait_time = min(
                max_wait,
                min_wait * (multiplier ** (attempt - 1)),
            )

        error_type = type(exception).__name__ if exception else "Unknown"
        error_message = str(exception)[:200] if exception else ""

        # Логируем через log_event
        log_event(
            event=f"{service_name}_retry",
            status="warning",
            extra={
                "attempt": attempt,
                "max_attempts": max_attempts,
                "error": error_type,
                "error_message": error_message,
                "wait_time": wait_time,
                "method": method_name or "unknown",
            },
            level="warning",
            message=f"Retry attempt {attempt}/{max_attempts} for {service_name} API request",
        )

        # Обновляем метрики
        try:
            from utils.prometheus_metrics import HTTP_RETRIES_TOTAL, HTTP_RETRY_WAIT_SECONDS

            HTTP_RETRIES_TOTAL.labels(service=service_name, method=method_name or "unknown", status="retry").inc()
            HTTP_RETRY_WAIT_SECONDS.labels(service=service_name, method=method_name or "unknown").observe(wait_time)
        except Exception:
            # Метрики не критичны, игнорируем ошибки
            pass

    def after_callback(retry_state: RetryCallState) -> None:
        """Логирует финальную ошибку после всех попыток."""
        if retry_state.outcome and retry_state.outcome.failed:
            exception = retry_state.outcome.exception()
            error_type = type(exception).__name__ if exception else "Unknown"
            error_message = str(exception)[:200] if exception else ""

            log_event(
                event=f"{service_name}_retry_failed",
                status="error",
                extra={
                    "max_attempts": max_attempts,
                    "error": error_type,
                    "error_message": error_message,
                    "method": method_name or "unknown",
                },
                level="error",
                message=f"All {max_attempts} retry attempts exhausted for {service_name} API request",
            )

            # Обновляем метрики
            try:
                from utils.prometheus_metrics import HTTP_RETRIES_TOTAL

                HTTP_RETRIES_TOTAL.labels(service=service_name, method=method_name or "unknown", status="failed").inc()
            except Exception:
                # Метрики не критичны, игнорируем ошибки
                pass

    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
        retry=retry_condition,
        before_sleep=before_sleep_callback,
        after=after_callback,
        reraise=True,
    )


def retry_critical(
    service_name: str,
    method_name: str | None = None,
    max_attempts: int | None = None,
) -> Callable[[F], F]:
    """
    Декоратор retry для критичных операций (5 попыток по умолчанию).

    Используется для критичных операций, таких как получение токена доступа.

    Args:
        service_name: Имя сервиса (например, "kandinsky", "gigachat")
        method_name: Имя метода для логирования (опционально)
        max_attempts: Максимальное количество попыток (по умолчанию из конфига)

    Returns:
        Декоратор retry
    """
    attempts = max_attempts or config.retry_max_attempts

    def decorator(func: F) -> F:
        method = method_name or func.__name__
        retry_decorator = _create_retry_decorator(
            max_attempts=attempts,
            multiplier=config.retry_multiplier,
            min_wait=config.retry_min_wait,
            max_wait=config.retry_max_wait,
            service_name=service_name,
            method_name=method,
        )

        @wraps(func)
        @retry_decorator
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def retry_standard(
    service_name: str,
    method_name: str | None = None,
    max_attempts: int = 3,
) -> Callable[[F], F]:
    """
    Декоратор retry для стандартных операций (3 попытки).

    Используется для обычных HTTP-запросов.

    Args:
        service_name: Имя сервиса (например, "kandinsky", "gigachat")
        method_name: Имя метода для логирования (опционально)
        max_attempts: Максимальное количество попыток (по умолчанию 3)

    Returns:
        Декоратор retry
    """

    def decorator(func: F) -> F:
        method = method_name or func.__name__
        retry_decorator = _create_retry_decorator(
            max_attempts=max_attempts,
            multiplier=config.retry_multiplier,
            min_wait=config.retry_min_wait,
            max_wait=config.retry_max_wait,
            service_name=service_name,
            method_name=method,
        )

        @wraps(func)
        @retry_decorator
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def retry_optional(
    service_name: str,
    method_name: str | None = None,
    max_attempts: int = 2,
) -> Callable[[F], F]:
    """
    Декоратор retry для необязательных операций (2 попытки).

    Используется для операций, которые не критичны для работы системы.

    Args:
        service_name: Имя сервиса (например, "kandinsky", "gigachat")
        method_name: Имя метода для логирования (опционально)
        max_attempts: Максимальное количество попыток (по умолчанию 2)

    Returns:
        Декоратор retry
    """

    def decorator(func: F) -> F:
        method = method_name or func.__name__
        retry_decorator = _create_retry_decorator(
            max_attempts=max_attempts,
            multiplier=config.retry_multiplier,
            min_wait=config.retry_min_wait,
            max_wait=config.retry_max_wait,
            service_name=service_name,
            method_name=method,
        )

        @wraps(func)
        @retry_decorator
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


# Универсальный декоратор для обратной совместимости
def retry_with_logging(
    service_name: str,
    method_name: str | None = None,
    max_attempts: int | None = None,
) -> Callable[[F], F]:
    """
    Универсальный декоратор retry с логированием (использует настройки из конфига).

    Args:
        service_name: Имя сервиса (например, "kandinsky", "gigachat")
        method_name: Имя метода для логирования (опционально)
        max_attempts: Максимальное количество попыток (по умолчанию из конфига)

    Returns:
        Декоратор retry
    """
    attempts = max_attempts or config.retry_max_attempts
    return retry_critical(service_name=service_name, method_name=method_name, max_attempts=attempts)
