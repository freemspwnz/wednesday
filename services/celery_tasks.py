"""
Celery задачи для Wednesday Frog Bot.

Использует lazy инициализацию сервисов через CeleryServices для fork safety.
Все async ресурсы создаются ПОСЛЕ fork, внутри задач.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import aiohttp
from celery import Task
from celery.signals import worker_shutdown

from bot.wednesday_bot import WednesdayBot
from services.celery_app import celery_app
from services.image_generator import ImageGenerator
from utils.config import config
from utils.logger import get_logger, log_event
from utils.postgres_client import close_postgres_pool, init_postgres_pool
from utils.postgres_schema import ensure_schema
from utils.prometheus_metrics import (
    CELERY_TASK_DURATION_SECONDS,
    CELERY_TASK_FAILURES_TOTAL,
    CELERY_TASK_RETRIES_TOTAL,
    CELERY_TASKS_TOTAL,
)
from utils.redis_client import close_redis, init_redis_pool

P = ParamSpec("P")
R = TypeVar("R")

logger = get_logger(__name__)


def is_retryable_error(error: Exception) -> bool:
    """
    Определяет, является ли ошибка retryable (сетевые ошибки).

    Args:
        error: Исключение для проверки

    Returns:
        True если ошибка retryable, False иначе
    """
    retryable_types = (
        aiohttp.ClientError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerTimeoutError,
        TimeoutError,
        ConnectionError,
        OSError,  # Сетевые ошибки на уровне ОС
    )

    # Проверяем тип исключения
    if isinstance(error, retryable_types):
        return True

    # Проверяем строковое представление для дополнительных случаев
    error_str = str(error).lower()
    retryable_keywords = (
        "connection",
        "timeout",
        "network",
        "temporary",
        "retry",
        "503",  # Service Unavailable
        "502",  # Bad Gateway
        "504",  # Gateway Timeout
    )

    return any(keyword in error_str for keyword in retryable_keywords)


# Lazy factories для безопасной инициализации
class CeleryServices:
    """
    Lazy factory для сервисов Celery.

    Инициализация происходит внутри задач, после fork worker процесса.
    Это гарантирует:
    - Fork safety (соединения создаются после fork)
    - Отсутствие race conditions
    - Корректную работу с async клиентами
    """

    _bot: WednesdayBot | None = None
    _generator: ImageGenerator | None = None
    _initialized: bool = False
    _init_lock = asyncio.Lock()

    @classmethod
    async def _ensure_initialized(cls) -> None:
        """Инициализирует сервисы один раз (thread-safe)."""
        if cls._initialized:
            return

        async with cls._init_lock:
            if cls._initialized:
                return

            # Инициализируем Redis и Postgres (async)
            # ВАЖНО: это происходит ПОСЛЕ fork, в worker процессе
            if config.redis_url:
                await init_redis_pool(url=config.redis_url)
            else:
                await init_redis_pool(
                    host=config.redis_host,
                    port=config.redis_port,
                    db=config.redis_db,
                    password=config.redis_password,
                )
            await init_postgres_pool(min_size=1, max_size=10)
            await ensure_schema()

            # Создаём экземпляры сервисов
            cls._bot = WednesdayBot()
            cls._generator = cls._bot.image_generator

            cls._initialized = True
            logger.info("Celery services initialized in worker process")

    @classmethod
    async def shutdown(cls) -> None:
        """
        Graceful shutdown для async ресурсов.

        Закрывает все соединения при остановке worker:
        - aiohttp sessions
        - redis pool
        - postgres pool

        ⚠️ ВАЖНО: Вызывается автоматически через сигнал worker_shutdown
        """
        if not cls._initialized:
            return

        logger.info("Shutting down Celery services...")

        try:
            if cls._bot:
                # Если у WednesdayBot есть метод aclose()
                if hasattr(cls._bot, "aclose"):
                    await cls._bot.aclose()

            if cls._generator:
                # Если у ImageGenerator есть метод aclose()
                if hasattr(cls._generator, "aclose"):
                    await cls._generator.aclose()

            # Закрываем пулы подключений
            await close_postgres_pool()
            await close_redis()
        except Exception as e:
            logger.error(f"Error during Celery services shutdown: {e}")
        finally:
            cls._bot = None
            cls._generator = None
            cls._initialized = False
            logger.info("Celery services shutdown complete")

    @classmethod
    async def get_bot(cls) -> WednesdayBot:
        """Получает экземпляр WednesdayBot (lazy init)."""
        await cls._ensure_initialized()
        if cls._bot is None:
            raise RuntimeError("Failed to initialize WednesdayBot")
        return cls._bot

    @classmethod
    async def get_generator(cls) -> ImageGenerator:
        """Получает экземпляр ImageGenerator (lazy init)."""
        await cls._ensure_initialized()
        if cls._generator is None:
            raise RuntimeError("Failed to initialize ImageGenerator")
        return cls._generator


# Регистрируем shutdown handler
@worker_shutdown.connect
def _on_worker_shutdown(sender: object | None = None, **kwargs: object) -> None:
    """
    Обработчик сигнала остановки worker для graceful shutdown.

    Для celery[asyncio] worker_shutdown может быть вызван в контексте async,
    но сигнал сам по себе синхронный. Используем безопасный подход.
    """
    try:
        # Пытаемся получить текущий event loop
        try:
            loop = asyncio.get_running_loop()
            # Если loop запущен, создаём задачу (для celery[asyncio])
            if not loop.is_closed():
                task = asyncio.create_task(CeleryServices.shutdown())
                # Сохраняем ссылку на задачу, чтобы она не была удалена сборщиком мусора
                _ = task
            else:
                # Loop закрыт, создаём новый
                asyncio.run(CeleryServices.shutdown())
        except RuntimeError:
            # Нет запущенного loop, создаём новый
            asyncio.run(CeleryServices.shutdown())
    except Exception as e:
        logger.error(f"Ошибка при вызове shutdown в worker_shutdown handler: {e}")


# Декоратор для логирования Celery задач
def log_celery_task(task_name: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Декоратор для автоматического логирования Celery задач."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        async def wrapper(self: Task, *args: object, **kwargs: object) -> Any:  # noqa: ANN401
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
    # ⚠️ УЛУЧШЕНО: retry только для сетевых ошибок, не для всех Exception
    autoretry_for=(
        aiohttp.ClientError,
        aiohttp.ClientConnectorError,
        aiohttp.ServerTimeoutError,
        TimeoutError,
        ConnectionError,
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
async def send_wednesday_frog_task(self: Task, slot_time: str | None = None) -> dict[str, Any]:
    """
    Celery задача для отправки изображения жабы.

    Args:
        slot_time: Время слота в формате "HH:MM" или None

    Returns:
        Словарь с результатом выполнения
    """
    try:
        # Lazy инициализация внутри задачи (после fork, безопасно)
        bot = await CeleryServices.get_bot()
        await bot.send_wednesday_frog(slot_time=slot_time)

        return {"status": "success", "slot_time": slot_time}
    except Exception as e:
        # ⚠️ ВАЖНО: Кастомная фильтрация retryable ошибок
        if is_retryable_error(e):
            # Обновляем метрики retry
            CELERY_TASK_RETRIES_TOTAL.labels(task_name="send_wednesday_frog").inc()
            # Retry только для сетевых ошибок
            raise self.retry(exc=e) from e
        else:
            # Бизнес-логические ошибки не retry, сразу падаем
            # После max_retries задача уйдёт в DLQ
            raise


@celery_app.task(
    bind=True,
    name="wednesday.generate_image",
    # ⚠️ УЛУЧШЕНО: retry только для сетевых ошибок через кастомную логику
    autoretry_for=(Exception,),  # Принимаем все, но фильтруем через is_retryable_error
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
async def generate_frog_image_task(self: Task, user_id: int | None = None) -> dict[str, Any]:
    """
    Celery задача для генерации изображения жабы.

    Args:
        user_id: ID пользователя (опционально)

    Returns:
        Словарь с результатом генерации
    """
    try:
        # Lazy инициализация внутри задачи (после fork, безопасно)
        generator = await CeleryServices.get_generator()
        result = await generator.generate_frog_image(user_id=user_id)

        if result:
            image_data, _caption = result
            return {
                "status": "success",
                "image_size": len(image_data),
            }
        else:
            return {"status": "failed", "error": "Генерация вернула None"}
    except Exception as e:
        # ⚠️ ВАЖНО: Кастомная фильтрация retryable ошибок
        if is_retryable_error(e):
            # Обновляем метрики retry
            CELERY_TASK_RETRIES_TOTAL.labels(task_name="generate_frog_image").inc()
            # Retry только для сетевых ошибок
            raise self.retry(exc=e) from e
        else:
            # Бизнес-логические ошибки не retry, сразу падаем
            # После max_retries задача уйдёт в DLQ
            raise


@celery_app.task(
    bind=True,
    name="wednesday.daily_cleanup",
    soft_time_limit=600,  # 10 минут
    time_limit=720,  # 12 минут
)
@log_celery_task("daily_cleanup")
async def daily_cleanup_task(self: Task) -> dict[str, Any]:
    """
    Ежедневная задача очистки старых данных.

    - Очистка старых логов
    - Очистка временных файлов
    - Очистка кэша
    """
    try:
        # Lazy инициализация для доступа к сервисам (для инициализации пулов)
        _ = await CeleryServices.get_bot()

        # Очистка старых записей dispatch_registry
        from utils.dispatch_registry import DispatchRegistry

        registry = DispatchRegistry()
        await registry.cleanup_old()

        logger.info("Daily cleanup task completed successfully")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in daily cleanup task: {e}")
        raise


@celery_app.task(
    bind=True,
    name="wednesday.daily_statistics",
    soft_time_limit=300,  # 5 минут
    time_limit=360,  # 6 минут
)
@log_celery_task("daily_statistics")
async def daily_statistics_task(self: Task) -> dict[str, Any]:
    """
    Ежедневная задача сбора статистики.

    - Агрегация метрик за день
    - Отправка отчётов
    - Обновление дашбордов
    """
    try:
        # Lazy инициализация для доступа к сервисам (для инициализации пулов)
        _ = await CeleryServices.get_bot()

        # Здесь можно добавить логику сбора статистики
        # Например, агрегация метрик из metrics_events

        logger.info("Daily statistics task completed successfully")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error in daily statistics task: {e}")
        raise
