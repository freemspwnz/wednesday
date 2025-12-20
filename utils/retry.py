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

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, TypeVar

import aiohttp
import httpx
from telegram.error import NetworkError, TelegramError, TimedOut
from tenacity import (
    retry,
    retry_base,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

if TYPE_CHECKING:
    from tenacity import RetryCallState
    from tenacity.wait import wait_base
else:
    from tenacity.wait import wait_base

from utils.config import config
from utils.logger import get_logger, log_event

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])

# Логгер для tenacity
_tenacity_logger = get_logger(__name__)

# HTTP-статусы, для которых не нужно делать retry
_NO_RETRY_STATUS_CODES = {400, 401, 403}

# HTTP статус для rate limit
HTTP_STATUS_RATE_LIMIT = 429


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


def retry_critical(  # noqa: PLR0913, PLR0917
    service_name: str,
    method_name: str | None = None,
    max_attempts: int | None = None,
    multiplier: float | None = None,
    min_wait: float | None = None,
    max_wait: float | None = None,
) -> Callable[[F], F]:
    """
    Декоратор retry для критичных операций.

    Используется для критичных операций, таких как получение токена доступа.

    Args:
        service_name: Имя сервиса (например, "kandinsky", "gigachat")
        method_name: Имя метода для логирования (опционально)
        max_attempts: Максимальное количество попыток (по умолчанию из RetryConfig)
        multiplier: Множитель для экспоненциального backoff (по умолчанию из RetryConfig)
        min_wait: Минимальное время ожидания (по умолчанию из RetryConfig)
        max_wait: Максимальное время ожидания (по умолчанию из RetryConfig)

    Returns:
        Декоратор retry
    """
    retry_cfg = config.get_retry_config()

    attempts = max_attempts or retry_cfg.critical_max_attempts
    mult = multiplier or retry_cfg.multiplier
    min_w = min_wait or retry_cfg.min_wait
    max_w = max_wait or retry_cfg.max_wait

    def decorator(func: F) -> F:
        method = method_name or func.__name__
        retry_decorator = _create_retry_decorator(
            max_attempts=attempts,
            multiplier=mult,
            min_wait=min_w,
            max_wait=max_w,
            service_name=service_name,
            method_name=method,
        )

        @wraps(func)
        @retry_decorator
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def retry_standard(  # noqa: PLR0913, PLR0917
    service_name: str,
    method_name: str | None = None,
    max_attempts: int | None = None,
    multiplier: float | None = None,
    min_wait: float | None = None,
    max_wait: float | None = None,
) -> Callable[[F], F]:
    """
    Декоратор retry для стандартных операций.

    Используется для обычных HTTP-запросов.

    Args:
        service_name: Имя сервиса (например, "kandinsky", "gigachat")
        method_name: Имя метода для логирования (опционально)
        max_attempts: Максимальное количество попыток (по умолчанию из RetryConfig)
        multiplier: Множитель для экспоненциального backoff (по умолчанию из RetryConfig)
        min_wait: Минимальное время ожидания (по умолчанию из RetryConfig)
        max_wait: Максимальное время ожидания (по умолчанию из RetryConfig)

    Returns:
        Декоратор retry
    """
    retry_cfg = config.get_retry_config()

    attempts = max_attempts or retry_cfg.standard_max_attempts
    mult = multiplier or retry_cfg.multiplier
    min_w = min_wait or retry_cfg.min_wait
    max_w = max_wait or retry_cfg.max_wait

    def decorator(func: F) -> F:
        method = method_name or func.__name__
        retry_decorator = _create_retry_decorator(
            max_attempts=attempts,
            multiplier=mult,
            min_wait=min_w,
            max_wait=max_w,
            service_name=service_name,
            method_name=method,
        )

        @wraps(func)
        @retry_decorator
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def retry_optional(  # noqa: PLR0913, PLR0917
    service_name: str,
    method_name: str | None = None,
    max_attempts: int | None = None,
    multiplier: float | None = None,
    min_wait: float | None = None,
    max_wait: float | None = None,
) -> Callable[[F], F]:
    """
    Декоратор retry для необязательных операций.

    Используется для операций, которые не критичны для работы системы.

    Args:
        service_name: Имя сервиса (например, "kandinsky", "gigachat")
        method_name: Имя метода для логирования (опционально)
        max_attempts: Максимальное количество попыток (по умолчанию из RetryConfig)
        multiplier: Множитель для экспоненциального backoff (по умолчанию из RetryConfig)
        min_wait: Минимальное время ожидания (по умолчанию из RetryConfig)
        max_wait: Максимальное время ожидания (по умолчанию из RetryConfig)

    Returns:
        Декоратор retry
    """
    retry_cfg = config.get_retry_config()

    attempts = max_attempts or retry_cfg.optional_max_attempts
    mult = multiplier or retry_cfg.multiplier
    min_w = min_wait or retry_cfg.min_wait
    max_w = max_wait or retry_cfg.max_wait

    def decorator(func: F) -> F:
        method = method_name or func.__name__
        retry_decorator = _create_retry_decorator(
            max_attempts=attempts,
            multiplier=mult,
            min_wait=min_w,
            max_wait=max_w,
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


# Константа для дефолтного значения retry_after при 429 ошибке
RETRY_AFTER_DEFAULT_SECONDS = 60


class WaitTelegramLinear(wait_base):
    """
    Кастомная стратегия ожидания для Telegram API с линейным backoff.

    Для обычных ошибок использует линейный backoff: delay * attempt_number.
    Для 429 ошибок (rate limit) использует retry_after из атрибута/заголовков.
    """

    def __init__(self, delay: float = 2.0) -> None:
        """
        Инициализирует стратегию ожидания.

        Args:
            delay: Базовая задержка между попытками (в секундах).
        """
        super().__init__()
        self.delay = delay

    def __call__(self, retry_state: RetryCallState) -> float:
        """
        Вычисляет время ожидания перед следующей попыткой.

        Args:
            retry_state: Состояние retry от tenacity с информацией о попытке и исключении.

        Returns:
            Время ожидания в секундах.
        """
        if not retry_state.outcome or not retry_state.outcome.failed:
            return self.delay * retry_state.attempt_number

        exception = retry_state.outcome.exception()
        if not exception:
            return self.delay * retry_state.attempt_number

        # Проверяем, является ли это 429 ошибкой (rate limit)
        is_429 = False
        retry_after: int | None = None

        if isinstance(exception, TelegramError):
            # Проверяем code == 429
            if hasattr(exception, "code") and exception.code == HTTP_STATUS_RATE_LIMIT:
                is_429 = True
            # Fallback: проверка строки ошибки
            elif not is_429:
                error_str = str(exception).lower()
                is_429 = "429" in error_str or "rate limit" in error_str or "too many requests" in error_str

            if is_429:
                # Приоритет 1: exception.retry_after
                if hasattr(exception, "retry_after") and exception.retry_after:
                    try:
                        retry_after = int(exception.retry_after)
                    except (ValueError, TypeError):
                        pass

                # Приоритет 2: заголовки ответа
                if retry_after is None and hasattr(exception, "response") and exception.response:
                    retry_after_header = exception.response.headers.get("retry-after")
                    if retry_after_header:
                        try:
                            retry_after = int(retry_after_header)
                        except (ValueError, TypeError):
                            pass

                # Приоритет 3: дефолт
                if retry_after is None:
                    retry_after = RETRY_AFTER_DEFAULT_SECONDS

                return float(retry_after)

        # Для остальных ошибок используем линейный backoff
        return self.delay * retry_state.attempt_number


def _should_retry_telegram_error(retry_state: RetryCallState) -> bool:
    """
    Предикат для определения, нужно ли делать retry для Telegram-ошибки.

    Retry для:
    - NetworkError, TimedOut (всегда True)
    - httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout (всегда True)
    - TelegramError только если exception.code == 429

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

    # NetworkError, TimedOut - всегда retry
    if isinstance(exception, NetworkError | TimedOut):
        return True

    # httpx исключения - всегда retry
    if isinstance(exception, httpx.ConnectError | httpx.ConnectTimeout | httpx.ReadTimeout):
        return True

    # TelegramError - только если code == 429
    if isinstance(exception, TelegramError):
        if hasattr(exception, "code") and exception.code == HTTP_STATUS_RATE_LIMIT:
            return True
        # Fallback: проверка строки ошибки
        error_str = str(exception).lower()
        if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str:
            return True
        return False

    return False


async def retry_on_connect_error(
    func: Callable[..., Awaitable[T]],
    *args: object,
    max_retries: int = 3,
    delay: float = 2.0,
    handle_rate_limit: bool = True,
    **kwargs: object,
) -> T:
    """
    Выполняет функцию с повторными попытками при сетевых/Telegram-ошибках.

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
    import asyncio

    wait_strategy = WaitTelegramLinear(delay=delay)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e

            # Создаём mock retry_state для проверки предиката
            # Это нужно для использования _should_retry_telegram_error
            class MockOutcome:
                def __init__(self, exc: Exception) -> None:
                    self._exc = exc
                    self.failed = True

                def exception(self) -> Exception | None:
                    return self._exc

            class MockRetryState:
                def __init__(self, attempt_num: int, exc: Exception) -> None:
                    self.attempt_number = attempt_num
                    self.outcome: MockOutcome = MockOutcome(exc)
                    self.next_action = None

            retry_state: Any = MockRetryState(attempt, e)

            # Проверяем, нужно ли делать retry
            if not _should_retry_telegram_error(retry_state):
                # Не делаем retry - пробрасываем исключение
                raise

            # Если это последняя попытка, пробрасываем исключение
            if attempt >= max_retries:
                raise

            # Вычисляем время ожидания
            wait_time = wait_strategy(retry_state)

            # Логируем попытку
            error_type = type(e).__name__
            error_message = str(e)[:200]

            log_event(
                event="telegram_retry",
                status="warning",
                extra={
                    "attempt": attempt,
                    "max_attempts": max_retries,
                    "error": error_type,
                    "error_message": error_message,
                    "wait_time": wait_time,
                },
                level="warning",
                message=f"Retry attempt {attempt}/{max_retries} for Telegram API request",
            )

            # Обновляем метрики
            try:
                from utils.prometheus_metrics import HTTP_RETRIES_TOTAL, HTTP_RETRY_WAIT_SECONDS

                HTTP_RETRIES_TOTAL.labels(service="telegram", method="unknown", status="retry").inc()
                HTTP_RETRY_WAIT_SECONDS.labels(service="telegram", method="unknown").observe(wait_time)
            except Exception:
                # Метрики не критичны, игнорируем ошибки
                pass

            # Ждём перед следующей попыткой
            await asyncio.sleep(wait_time)

    # Если дошли сюда, все попытки исчерпаны
    if last_error:
        # Логируем финальную ошибку
        error_type = type(last_error).__name__
        error_message = str(last_error)[:200]

        log_event(
            event="telegram_retry_failed",
            status="error",
            extra={
                "max_attempts": max_retries,
                "error": error_type,
                "error_message": error_message,
            },
            level="error",
            message=f"All {max_retries} retry attempts exhausted for Telegram API request",
        )

        # Обновляем метрики
        try:
            from utils.prometheus_metrics import HTTP_RETRIES_TOTAL

            HTTP_RETRIES_TOTAL.labels(service="telegram", method="unknown", status="failed").inc()
        except Exception:
            # Метрики не критичны, игнорируем ошибки
            pass

        raise last_error

    # Это не должно произойти, но на всякий случай
    raise RuntimeError("Unexpected error in retry_on_connect_error")


def retry_telegram(
    max_retries: int = 3,
    delay: float = 2.0,
    handle_rate_limit: bool = True,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Декоратор для типичных retry-паттернов вокруг Telegram-хелперов.

    Используется для обёртки методов, которые делают один или несколько вызовов
    Telegram API (send_message, send_photo и т.п.).

    Args:
        max_retries: Максимальное количество попыток.
        delay: Базовая задержка между попытками (в секундах).
        handle_rate_limit: Если True, обрабатывает TelegramError с кодом 429 (rate limit).

    Returns:
        Декоратор retry.
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
