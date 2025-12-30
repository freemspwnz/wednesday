"""
Celery задачи для Wednesday Frog Bot с использованием нового WorkerContext.

Все задачи определены как async def и используют worker_ctx.get_container()
для получения контейнера с сервисами через Dependency Injection.

⚠️ ВАЖНО: В этом файле должна быть только логика вызова сервисов.
Никаких прямых обращений к БД или Redis.
"""

from __future__ import annotations

import functools
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeVar

from celery import Task

from infra.celery.app import celery_app
from infra.celery.new_context import worker_ctx
from infra.logging.logger import get_logger, log_event
from infra.metrics.prometheus_metrics import (
    CELERY_TASK_DURATION_SECONDS,
    CELERY_TASK_FAILURES_TOTAL,
    CELERY_TASKS_TOTAL,
)

if TYPE_CHECKING:
    from shared.bot_services import BotServices

R = TypeVar("R")

logger = get_logger(__name__)


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
        async def my_task(self: Task) -> dict:
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


def with_container(func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
    """Декоратор для автоматического получения Container через worker_ctx.

    Инъектирует services: BotServices в kwargs задачи.

    Args:
        func: Асинхронная функция задачи.

    Returns:
        Обёрнутая функция с инъекцией services.

    Example:
        @celery_app.task(bind=True, name="my.task")
        @log_celery_task("my_task")
        @with_container
        async def my_task(self: Task, *, services: BotServices) -> dict:
            await services.image_service.generate_image(...)
            ...
    """

    @functools.wraps(func)
    async def wrapper(self: Task, *args: object, **kwargs: object) -> R:
        # Получаем контейнер через worker_ctx (singleton)
        container = await worker_ctx.get_container()

        # Получаем сервисы из контейнера
        services = container.build_bot_services()

        # Инъекция services через kwargs
        kwargs["services"] = services

        return await func(self, *args, **kwargs)

    return wrapper


# Пример задачи: отправка жабы по расписанию
@celery_app.task(
    bind=True,
    name="wednesday.new_send_frog",
    soft_time_limit=300,  # 5 минут
    time_limit=360,  # 6 минут (hard limit)
    options={"queue": "wednesday"},
)
@log_celery_task("new_send_wednesday_frog")
@with_container
async def new_send_frog(  # noqa: RUF029
    self: Task,
    slot_time: str | None = None,
    *,
    services: BotServices,
) -> dict[str, str]:
    """Отправляет изображение жабы по расписанию.

    ⚠️ ВАЖНО: Использует только сервисы из контейнера.
    Никаких прямых обращений к БД или Redis.

    Args:
        self: Экземпляр Task от Celery.
        slot_time: Опциональное время слота в формате "HH:MM".
        services: Сервисы бота (инъектируются через @with_container).

    Returns:
        Словарь с результатом выполнения задачи.
    """
    logger.info(
        f"Начало выполнения задачи отправки жабы (slot_time={slot_time})",
        event="new_send_frog_started",
        status="in_progress",
    )

    try:
        # Используем сервисы из контейнера
        # Пример: await services.dispatch_service.send_to_all_chats(slot_time=slot_time)
        # В реальной реализации здесь будет вызов соответствующего сервиса

        logger.info(
            f"Задача отправки жабы выполнена успешно (slot_time={slot_time})",
            event="new_send_frog_success",
            status="ok",
        )

        return {
            "status": "success",
            "slot_time": slot_time or "auto",
            "message": "Frog sent successfully",
        }

    except Exception as e:
        logger.error(
            f"Ошибка при выполнении задачи отправки жабы: {e}",
            event="new_send_frog_error",
            status="error",
            error_type=type(e).__name__,
            error_message=str(e),
        )
        raise


# Пример задачи: генерация изображения
@celery_app.task(
    bind=True,
    name="wednesday.new_generate_image",
    soft_time_limit=180,  # 3 минуты
    time_limit=240,  # 4 минуты (hard limit)
    options={"queue": "images"},
)
@log_celery_task("new_generate_image")
@with_container
async def new_generate_image(  # noqa: RUF029
    self: Task,
    prompt: str,
    *,
    services: BotServices,
) -> dict[str, str]:
    """Генерирует изображение через ImageService.

    ⚠️ ВАЖНО: Использует только сервисы из контейнера.
    Никаких прямых обращений к БД или Redis.

    Args:
        self: Экземпляр Task от Celery.
        prompt: Промпт для генерации изображения.
        services: Сервисы бота (инъектируются через @with_container).

    Returns:
        Словарь с результатом генерации.
    """
    logger.info(
        f"Начало генерации изображения (prompt={prompt[:50]}...)",
        event="new_generate_image_started",
        status="in_progress",
    )

    try:
        # Используем сервисы из контейнера
        # Пример: result = await services.image_service.generate_image(prompt=prompt)
        # В реальной реализации здесь будет вызов ImageService

        logger.info(
            "Генерация изображения выполнена успешно",
            event="new_generate_image_success",
            status="ok",
        )

        return {
            "status": "success",
            "prompt": prompt,
            "message": "Image generated successfully",
        }

    except Exception as e:
        logger.error(
            f"Ошибка при генерации изображения: {e}",
            event="new_generate_image_error",
            status="error",
            error_type=type(e).__name__,
            error_message=str(e),
        )
        raise


# Пример задачи: ежедневная очистка
@celery_app.task(
    bind=True,
    name="wednesday.new_daily_cleanup",
    soft_time_limit=600,  # 10 минут
    time_limit=720,  # 12 минут (hard limit)
    options={"queue": "maintenance"},
)
@log_celery_task("new_daily_cleanup")
@with_container
async def new_daily_cleanup(  # noqa: RUF029
    self: Task,
    *,
    services: BotServices,
) -> dict[str, str]:
    """Выполняет ежедневную очистку данных.

    ⚠️ ВАЖНО: Использует только сервисы из контейнера.
    Никаких прямых обращений к БД или Redis.

    Args:
        self: Экземпляр Task от Celery.
        services: Сервисы бота (инъектируются через @with_container).

    Returns:
        Словарь с результатом очистки.
    """
    logger.info(
        "Начало ежедневной очистки",
        event="new_daily_cleanup_started",
        status="in_progress",
    )

    try:
        # Используем сервисы из контейнера
        # Пример: await services.data_cleanup_service.cleanup_old_data()
        # В реальной реализации здесь будет вызов DataCleanupService

        logger.info(
            "Ежедневная очистка выполнена успешно",
            event="new_daily_cleanup_success",
            status="ok",
        )

        return {
            "status": "success",
            "message": "Daily cleanup completed successfully",
        }

    except Exception as e:
        logger.error(
            f"Ошибка при ежедневной очистке: {e}",
            event="new_daily_cleanup_error",
            status="error",
            error_type=type(e).__name__,
            error_message=str(e),
        )
        raise
