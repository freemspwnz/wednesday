"""
Celery задачи для Wednesday Frog Bot.

Использует dependency injection через get_services_context() для fork safety.
Все async ресурсы создаются ПОСЛЕ fork, внутри задач.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

import aiohttp
from celery import Task

if TYPE_CHECKING:
    from bot.wednesday_bot import WednesdayBot
    from infra.celery.context import ServicesContext

from datetime import datetime

from infra.celery.app import celery_app
from infra.celery.context import get_or_create_worker_factories, get_services_context
from infra.logging.logger import get_logger, log_event
from infra.metrics.prometheus_metrics import (
    CELERY_TASK_DURATION_SECONDS,
    CELERY_TASK_FAILURES_TOTAL,
    CELERY_TASKS_TOTAL,
)
from shared.models import FrogRequestResult
from shared.protocols import (
    IFrogProcessingService,
    IIdempotencyService,
    IImageService,
)

R = TypeVar("R")
T = TypeVar("T")

logger = get_logger(__name__)


def _get_wednesday_bot(context: ServicesContext) -> WednesdayBot:
    """Получает WednesdayBot из контекста с проверкой типа.

    Использует ленивый импорт для избежания циклических зависимостей.

    Args:
        context: Контекст сервисов из get_services_context().

    Returns:
        Экземпляр WednesdayBot.

    Raises:
        RuntimeError: Если bot не найден в контексте или имеет неправильный тип.
    """
    from bot.wednesday_bot import WednesdayBot  # Ленивый импорт

    bot = context.get("bot")
    if not isinstance(bot, WednesdayBot):
        raise RuntimeError("Failed to get WednesdayBot from context")
    return bot


def _get_idempotency_service(context: ServicesContext) -> IIdempotencyService:
    """Получает IdempotencyService из контекста с проверкой типа.

    Args:
        context: Контекст сервисов из get_services_context().

    Returns:
        Экземпляр IIdempotencyService.

    Raises:
        RuntimeError: Если IdempotencyService не найден в контексте или имеет неправильный тип.
    """
    idempotency_service = context.get("idempotency_service")
    if not isinstance(idempotency_service, IIdempotencyService):
        raise RuntimeError("IdempotencyService is not available in context")
    return idempotency_service


def generate_daily_idempotency_key(task_name: str) -> str:
    """Генерирует ключ идемпотентности на основе текущей даты.

    Используется для ежедневных задач, которые должны выполняться только раз в день.

    Args:
        task_name: Имя задачи для включения в ключ.

    Returns:
        Ключ идемпотентности в формате "{task_name}:{YYYY-MM-DD}".
    """
    current_date = datetime.now().strftime("%Y-%m-%d")
    return f"{task_name}:{current_date}"


def generate_idempotency_key(task_name: str, **params: object) -> str:
    """Генерирует ключ идемпотентности на основе имени задачи и параметров.

    Универсальная функция для генерации ключей идемпотентности.
    Если параметры не переданы, использует ежедневный ключ.

    Args:
        task_name: Имя задачи для включения в ключ.
        **params: Параметры для включения в ключ (сортируются для консистентности).

    Returns:
        Ключ идемпотентности в формате "{task_name}:{param1=value1}:{param2=value2}..."
        или "{task_name}:{YYYY-MM-DD}" если параметры не переданы.

    Examples:
        >>> generate_idempotency_key("my_task", user_id=123, chat_id=456)
        "my_task:chat_id=456:user_id=123"
        >>> generate_idempotency_key("daily_task")
        "daily_task:2025-01-01"
    """
    if not params:
        return generate_daily_idempotency_key(task_name)

    # Сортируем параметры для консистентности ключей
    sorted_params = ":".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)
    return f"{task_name}:{sorted_params}"


async def execute_with_idempotency(
    context: ServicesContext,
    key: str,
    ttl: int,
    operation: Callable[[], Awaitable[T]],
) -> T:
    """Выполняет операцию с идемпотентностью через IdempotencyService.

    Helper-функция для упрощения использования идемпотентности в задачах.
    Устраняет дублирование кода получения сервиса из контекста.

    Args:
        context: Контекст сервисов.
        key: Ключ идемпотентности.
        ttl: Время жизни кэша в секундах.
        operation: Асинхронная операция для выполнения.

    Returns:
        Результат выполнения операции.
    """
    idempotency_service = _get_idempotency_service(context)
    return await idempotency_service.execute_with_idempotency(
        key=key,
        ttl=ttl,
        operation=operation,
    )


async def execute_daily_task_with_idempotency(
    context: ServicesContext,
    task_name: str,
    operation: Callable[[], Awaitable[T]],
) -> T:
    """Выполняет ежедневную задачу с идемпотентностью (TTL=24 часа).

    Упрощённый helper для ежедневных задач, которые должны выполняться только раз в день.

    Args:
        context: Контекст сервисов.
        task_name: Имя задачи (используется для генерации ключа идемпотентности).
        operation: Асинхронная операция для выполнения.

    Returns:
        Результат выполнения операции.
    """
    return await execute_with_idempotency(
        context=context,
        key=generate_daily_idempotency_key(task_name),
        ttl=86400,  # 24 часа
        operation=operation,
    )


def with_services_context(
    func: Callable[..., Awaitable[R]],
) -> Callable[..., Awaitable[R]]:
    """Декоратор для автоматического получения контекста сервисов в Celery задачах.

    Автоматически получает контекст сервисов через get_services_context() и передаёт
    его в задачу как именованный параметр 'context'. Устраняет дублирование кода
    получения контекста в каждой задаче.

    ⚠️ ВАЖНО: Задача должна быть объявлена с @celery_app.task(bind=True), так как
    декоратор ожидает self: Task первым аргументом.

    Args:
        func: Асинхронная функция задачи Celery.

    Returns:
        Обёрнутая функция, которая автоматически получает и передаёт context.

    Example:
        @celery_app.task(bind=True, name="my.task")
        @log_celery_task("my_task")
        @with_services_context
        async def my_task(self: Task, param: int, *, context: ServicesContext) -> dict:
            service = context.get("my_service")
            ...

    Note:
        Использует @functools.wraps для сохранения метаданных функции (имя, docstring),
        что критично для корректной регистрации задачи в Celery и работы инструментов
        мониторинга (Sentry, логирование и т.д.).
    """

    @functools.wraps(func)
    async def wrapper(self: Task, *args: object, **kwargs: object) -> R:
        # Получаем фабрики (кэшируются на worker процесс)
        from shared.config import Config

        pool_factory, redis_factory, config_obj = await get_or_create_worker_factories(Config())

        # Получаем контекст сервисов через DI
        context = await get_services_context(
            pool_factory=pool_factory,
            redis_factory=redis_factory,
            config_obj=config_obj,
        )

        # Инъекция контекста через kwargs
        kwargs["context"] = context

        return await func(self, *args, **kwargs)

    return wrapper


# Декоратор для логирования Celery задач
# Используем Any для args/kwargs, так как Celery задачи имеют разные сигнатуры
def log_celery_task(task_name: str) -> Callable[[Callable[..., Awaitable[R]]], Callable[..., Awaitable[R]]]:
    """Декоратор для автоматического логирования Celery задач.

    Декоратор добавляет автоматическое логирование начала, завершения и ошибок
    выполнения Celery задач, а также обновляет метрики Prometheus.

    Args:
        task_name: Имя задачи для логирования и метрик.

    Returns:
        Декоратор, который оборачивает асинхронную функцию задачи.

    Example:
        @log_celery_task("my_task")
        async def my_task(self: Task) -> dict[str, Any]:
            ...
    """

    def decorator(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        async def wrapper(self: Task, *args: object, **kwargs: object) -> R:
            start_time = time.time()
            # Получаем request из self (Task)
            request = getattr(self, "request", None)
            task_id = request.id if request else "unknown"

            try:
                # Обновляем метрики Prometheus
                CELERY_TASKS_TOTAL.labels(task_name=task_name, status="started").inc()

                log_event(
                    event="celery_task_started",
                    status="in_progress",
                    extra={
                        "task_name": task_name,
                        "task_id": task_id,
                    },
                    level="info",
                    message=f"Celery задача {task_name} запущена (task_id={task_id})",
                )

                result = await func(self, *args, **kwargs)

                elapsed = time.time() - start_time

                # Обновляем метрики Prometheus
                CELERY_TASKS_TOTAL.labels(task_name=task_name, status="success").inc()
                CELERY_TASK_DURATION_SECONDS.labels(task_name=task_name).observe(elapsed)

                log_event(
                    event="celery_task_success",
                    status="ok",
                    latency_ms=round(elapsed * 1000),
                    extra={
                        "task_name": task_name,
                        "task_id": task_id,
                    },
                    level="info",
                    message=f"Celery задача {task_name} завершена успешно за {elapsed:.2f}с",
                )

                return result

            except Exception as e:
                elapsed = time.time() - start_time

                # Обновляем метрики Prometheus
                error_type = type(e).__name__
                CELERY_TASKS_TOTAL.labels(task_name=task_name, status="failed").inc()
                CELERY_TASK_FAILURES_TOTAL.labels(task_name=task_name, error_type=error_type).inc()

                log_event(
                    event="celery_task_failed",
                    status="error",
                    latency_ms=round(elapsed * 1000),
                    extra={
                        "task_name": task_name,
                        "task_id": task_id,
                        "error": str(e),
                    },
                    level="error",
                    message=f"Celery задача {task_name} завершилась с ошибкой: {e}",
                )
                raise

        return wrapper

    return decorator


@celery_app.task(
    bind=True,
    name="wednesday.send_frog",
    # Retry только для сетевых ошибок
    autoretry_for=(
        aiohttp.ClientError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerTimeoutError,
        TimeoutError,
        ConnectionError,
        OSError,  # Сетевые ошибки на уровне ОС
    ),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    soft_time_limit=300,  # 5 минут
    time_limit=360,  # 6 минут (hard limit)
    options={"queue": "wednesday"},  # Явно указываем очередь
)
@log_celery_task("send_wednesday_frog")
@with_services_context
async def send_wednesday_frog_task(
    self: Task,
    slot_time: str | None = None,
    *,
    context: ServicesContext,
) -> dict[str, Any]:
    """Celery задача для отправки изображения жабы.

    Выполняет отправку изображения жабы всем подписанным пользователям в указанное
    время слота. Использует dependency injection через get_services_context().

    Args:
        self: Экземпляр Celery Task.
        slot_time: Время слота в формате "HH:MM" или None для текущего времени.
        context: Контекст сервисов (автоматически инжектируется декоратором).

    Returns:
        Словарь с результатом выполнения, содержащий:
        - status: Статус выполнения ("success" или "error").
        - slot_time: Время слота, в которое была выполнена отправка.

    Raises:
        Exception: При ошибке отправки или инициализации сервисов.
        Retry: При сетевых ошибках (автоматический retry через Celery).
    """
    try:
        # Генерируем ключ идемпотентности на основе slot_time или текущей даты
        idempotency_key = generate_idempotency_key("send_wednesday_frog", slot_time=slot_time)

        # Выполняем отправку с идемпотентностью через helper-функцию
        result = await execute_with_idempotency(
            context=context,
            key=idempotency_key,
            ttl=86400,  # 24 часа (чтобы не повторять отправку в течение дня)
            operation=lambda: _send_wednesday_frog_operation(context, slot_time),
        )

        return result
    except Exception:
        # Исключения пробрасываются для автоматического retry через autoretry_for
        # Celery автоматически обработает retry для сетевых ошибок, указанных в autoretry_for
        raise


async def _send_wednesday_frog_operation(
    context: ServicesContext,
    slot_time: str | None,
) -> dict[str, Any]:
    """Вспомогательная функция для выполнения отправки жабы.

    Вынесена отдельно для использования в idempotency_service.

    Args:
        context: Контекст сервисов.
        slot_time: Время слота в формате "HH:MM" или None.

    Returns:
        Словарь с результатом выполнения.
    """
    bot = _get_wednesday_bot(context)
    await bot.send_wednesday_frog(slot_time=slot_time)
    return {"status": "success", "slot_time": slot_time}


@celery_app.task(
    bind=True,
    name="wednesday.generate_image",
    # Retry только для сетевых ошибок
    autoretry_for=(
        aiohttp.ClientError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerTimeoutError,
        TimeoutError,
        ConnectionError,
        OSError,  # Сетевые ошибки на уровне ОС
    ),
    retry_kwargs={"max_retries": 2, "countdown": 30},
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    soft_time_limit=120,  # 2 минуты
    time_limit=150,  # 2.5 минуты (hard limit)
    options={"queue": "images"},  # Явно указываем очередь
    # ⚠️ ВАЖНО: Dead Letter Queue для задач, которые упали 2 раза
    reject_on_worker_lost=True,
    acks_late=True,
)
@log_celery_task("generate_frog_image")
@with_services_context
async def generate_frog_image_task(
    self: Task,
    user_id: int | None = None,
    *,
    context: ServicesContext,
) -> dict[str, Any]:
    """Celery задача для генерации изображения жабы.

    Выполняет генерацию изображения жабы через ImageService. Использует dependency
    injection через get_services_context().

    Args:
        self: Экземпляр Celery Task.
        user_id: ID пользователя, для которого выполняется генерация (опционально).
        context: Контекст сервисов (автоматически инжектируется декоратором).

    Returns:
        Словарь с результатом генерации, содержащий:
        - status: Статус выполнения ("success" или "failed").
        - image_size: Размер сгенерированного изображения в байтах (при успехе).

    Raises:
        Exception: При ошибке генерации или инициализации сервисов.
        Retry: При сетевых ошибках (автоматический retry через Celery).
    """
    try:
        # Генерируем ключ идемпотентности на основе user_id через helper-функцию
        idempotency_key = generate_idempotency_key("generate_frog_image", user_id=user_id)

        # Выполняем генерацию с идемпотентностью через helper-функцию
        result = await execute_with_idempotency(
            context=context,
            key=idempotency_key,
            ttl=3600,  # 1 час (чтобы не генерировать повторно для того же пользователя)
            operation=lambda: _generate_frog_image_operation(context, user_id),
        )

        return result
    except Exception:
        # Исключения пробрасываются для автоматического retry через autoretry_for
        # Celery автоматически обработает retry для сетевых ошибок, указанных в autoretry_for
        raise


async def _generate_frog_image_operation(
    context: ServicesContext,
    user_id: int | None,
) -> dict[str, Any]:
    """Вспомогательная функция для выполнения генерации изображения.

    Вынесена отдельно для использования в idempotency_service.

    Args:
        context: Контекст сервисов.
        user_id: ID пользователя (опционально).

    Returns:
        Словарь с результатом генерации.
    """
    image_service = context.get("image_service")
    if not isinstance(image_service, IImageService):
        raise RuntimeError("ImageService is not available in context")

    image_data, _caption = await image_service.generate_frog_image(user_id=user_id)

    return {
        "status": "success",
        "image_size": len(image_data),
    }


@celery_app.task(
    bind=True,
    name="wednesday.send_frog_manual",
    autoretry_for=(
        aiohttp.ClientError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerTimeoutError,
        TimeoutError,
        ConnectionError,
        OSError,  # Сетевые ошибки на уровне ОС
    ),
    retry_kwargs={"max_retries": 3, "countdown": 60},
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    soft_time_limit=300,  # 5 минут
    time_limit=360,  # 6 минут (hard limit)
    options={"queue": "wednesday"},
)
@log_celery_task("send_frog_manual")
@with_services_context
async def send_frog_manual(  # noqa: PLR0913
    self: Task,
    chat_id: int,
    user_id: int,
    status_message_id: int | None = None,
    idempotency_key: str | None = None,
    *,
    context: ServicesContext,
) -> FrogRequestResult:
    """Celery задача для отправки изображения жабы по ручной команде /frog.

    Теперь только оркестрирует выполнение, вся бизнес-логика в FrogProcessingService.
    Поддерживает идемпотентность через Redis кэширование результатов.

    Args:
        self: Экземпляр Celery Task.
        chat_id: ID чата для отправки изображения.
        user_id: ID пользователя.
        status_message_id: ID статусного сообщения для удаления (опционально).
        idempotency_key: Ключ идемпотентности для предотвращения дубликатов (опционально).
            Если не указан, генерируется автоматически на основе параметров.
        context: Контекст сервисов (автоматически инжектируется декоратором).

    Returns:
        FrogRequestResult с результатом выполнения.

    Raises:
        Exception: При ошибке обработки.
        Retry: При сетевых ошибках (автоматический retry через Celery).
    """
    try:
        # Получаем frog_processing из контекста (создан через DI)
        frog_processing = context.get("frog_processing")
        if not isinstance(frog_processing, IFrogProcessingService):
            raise RuntimeError("FrogProcessingService is not available in context")

        # Генерируем ключ идемпотентности, если не передан
        if idempotency_key is None:
            idempotency_key = generate_idempotency_key(
                "frog_manual",
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message_id,
            )

        # Выполняем обработку запроса с идемпотентностью через helper-функцию
        result = await execute_with_idempotency(
            context=context,
            key=idempotency_key,
            ttl=3600,  # 1 час
            operation=lambda: frog_processing.process_frog_request(
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message_id,
            ),
        )

        return result
    except Exception:
        # Исключения пробрасываются для автоматического retry через autoretry_for
        # Celery автоматически обработает retry для сетевых ошибок, указанных в autoretry_for
        raise


@celery_app.task(
    bind=True,
    name="wednesday.daily_cleanup",
    autoretry_for=(
        aiohttp.ClientError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerTimeoutError,
        TimeoutError,
        ConnectionError,
        OSError,  # Сетевые ошибки на уровне ОС
    ),
    retry_kwargs={"max_retries": 2, "countdown": 300},
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    soft_time_limit=600,  # 10 минут
    time_limit=720,  # 12 минут
)
@log_celery_task("daily_cleanup")
@with_services_context
async def daily_cleanup_task(
    self: Task,
    *,
    context: ServicesContext,
) -> dict[str, Any]:
    """Ежедневная задача очистки старых данных.

    Выполняет очистку устаревших данных через DataCleanupService:
    - Очистка старых записей dispatch_registry.
    - Очистка временных файлов (если добавлено в будущем).
    - Очистка кэша (если добавлено в будущем).

    Args:
        self: Экземпляр Celery Task.
        context: Контекст сервисов (автоматически инжектируется декоратором).

    Returns:
        Словарь с результатом выполнения, содержащий:
        - status: Статус выполнения ("success" или "error").

    Raises:
        Exception: При ошибке выполнения очистки.
        Retry: При сетевых ошибках (автоматический retry через Celery).
    """
    try:
        # Выполняем очистку с идемпотентностью через helper-функцию для ежедневных задач
        result = await execute_daily_task_with_idempotency(
            context=context,
            task_name="daily_cleanup",
            operation=lambda: _daily_cleanup_operation(context),
        )

        return result
    except Exception as e:
        # Исключения пробрасываются для автоматического retry через autoretry_for
        # Celery автоматически обработает retry для сетевых ошибок, указанных в autoretry_for
        logger.error(f"Error in daily cleanup task: {e}")
        raise


async def _daily_cleanup_operation(
    context: ServicesContext,
) -> dict[str, Any]:
    """Вспомогательная функция для выполнения ежедневной очистки.

    Вынесена отдельно для использования в idempotency_service.

    Args:
        context: Контекст сервисов.

    Returns:
        Словарь с результатом выполнения.
    """
    from shared.protocols import IDataCleanupService

    data_cleanup_service = context.get("data_cleanup_service")
    if not isinstance(data_cleanup_service, IDataCleanupService):
        raise RuntimeError("DataCleanupService is not available in context")

    # Выполняем очистку через сервис (соблюдение границ слоёв)
    await data_cleanup_service.cleanup_all()

    logger.info("Daily cleanup task completed successfully")
    return {"status": "success"}


@celery_app.task(
    bind=True,
    name="wednesday.daily_statistics",
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 300},
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    soft_time_limit=300,  # 5 минут
    time_limit=360,  # 6 минут
)
@log_celery_task("daily_statistics")
@with_services_context
async def daily_statistics_task(
    self: Task,
    *,
    context: ServicesContext,
) -> dict[str, Any]:
    """Ежедневная задача сбора статистики.

    Выполняет сбор и агрегацию статистики за день:
    - Агрегация метрик из metrics_events.
    - Отправка отчётов (если настроено).
    - Обновление дашбордов (если настроено).

    Args:
        self: Экземпляр Celery Task.
        context: Контекст сервисов (автоматически инжектируется декоратором).

    Returns:
        Словарь с результатом выполнения, содержащий:
        - status: Статус выполнения ("success" или "error").

    Raises:
        Exception: При ошибке сбора статистики.
        Retry: При сетевых ошибках (автоматический retry через Celery).
    """
    try:
        # Выполняем сбор статистики с идемпотентностью через helper-функцию для ежедневных задач
        result = await execute_daily_task_with_idempotency(
            context=context,
            task_name="daily_statistics",
            operation=lambda: _daily_statistics_operation(context),
        )

        return result
    except Exception as e:
        # Исключения пробрасываются для автоматического retry через autoretry_for
        # Celery автоматически обработает retry для сетевых ошибок, указанных в autoretry_for
        logger.error(f"Error in daily statistics task: {e}")
        raise


async def _daily_statistics_operation(  # noqa: RUF029
    context: ServicesContext,
) -> dict[str, Any]:
    """Вспомогательная функция для выполнения ежедневного сбора статистики.

    Вынесена отдельно для использования в idempotency_service.

    Args:
        context: Контекст сервисов.

    Returns:
        Словарь с результатом выполнения.
    """
    # Здесь можно добавить логику сбора статистики
    # Например, агрегация метрик из metrics_events
    # Контекст доступен через параметр context, если понадобится

    logger.info("Daily statistics task completed successfully")
    return {"status": "success"}


@celery_app.task(
    bind=True,
    name="wednesday.beat_heartbeat",
)
def beat_heartbeat(self: Task) -> dict[str, Any]:
    """Задача для heartbeat Beat (touch файл в tmpfs).

    Создаёт или обновляет файл heartbeat для мониторинга работы Celery Beat.
    Используется healthcheck-системами для проверки активности планировщика.

    Args:
        self: Экземпляр Celery Task.

    Returns:
        Словарь с результатом выполнения, содержащий:
        - status: Статус выполнения ("ok").

    Note:
        Ошибки при создании файла игнорируются, так как healthcheck сам проверит
        наличие файла.
    """
    import os

    heartbeat_path = "/tmp/beat-hb"
    try:
        # Touch файл (создать или обновить mtime)
        with open(heartbeat_path, "a", encoding="utf-8"):
            os.utime(heartbeat_path, None)
    except Exception:
        # Игнорируем ошибки - healthcheck сам проверит наличие файла
        pass

    return {"status": "ok"}
