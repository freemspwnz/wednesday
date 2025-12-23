"""
Инициализация и управление сервисами для Celery задач.

Обеспечивает fork-safe инициализацию сервисов в Celery worker процессах.
Все async ресурсы создаются ПОСЛЕ fork, внутри задач.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import asyncpg
from celery.signals import worker_shutdown

from infra.database.postgres_client import init_postgres_pool
from infra.database.postgres_schema import ensure_schema
from infra.logging.logger import get_logger
from infra.redis.redis_client import init_redis_pool
from shared.config import Config

if TYPE_CHECKING:
    from infra.cleanup_service import CleanupService
    from infra.redis.redis_client import RedisClient

# Создаём экземпляр Config при импорте модуля
config: Config = Config()

logger = get_logger(__name__)


# Context для хранения инициализированных сервисов в worker процессе
_services_context: dict[str, object] | None = None
_cleanup_service: CleanupService | None = None
_init_lock = asyncio.Lock()


async def _ensure_pools_initialized(
    config_obj: Config | None = None,
) -> tuple[asyncpg.Pool, RedisClient]:
    """Инициализирует пулы подключений Redis и Postgres.

    Инициализация происходит внутри задач, после fork worker процесса, что гарантирует:
    - Fork safety (соединения создаются после fork).
    - Отсутствие race conditions.

    Args:
        config_obj: Экземпляр Config. Если None, используется глобальный config.

    Returns:
        Кортеж (postgres_pool, redis_client) с инициализированными пулами.

    Raises:
        RuntimeError: Если не удалось инициализировать пулы подключений.
    """
    if config_obj is None:
        config_obj = config

    async with _init_lock:
        # Инициализируем Redis и Postgres (async)
        # ВАЖНО: это происходит ПОСЛЕ fork, в worker процессе
        redis_client: RedisClient
        try:
            if isinstance(config_obj, Config):
                if config_obj.redis.url:
                    redis_client = await init_redis_pool(url=config_obj.redis.url)
                else:
                    redis_client = await init_redis_pool(
                        host=config_obj.redis.host,
                        port=config_obj.redis.port,
                        db=config_obj.redis.db,
                        password=config_obj.redis.password,
                    )
            elif config_obj.redis_url:
                redis_client = await init_redis_pool(url=config_obj.redis_url)
            else:
                redis_client = await init_redis_pool(
                    host=config_obj.redis_host,
                    port=config_obj.redis_port,
                    db=config_obj.redis_db,
                    password=config_obj.redis_password,
                )
        except Exception as exc:
            # Redis не критичен для Celery worker — продолжаем с fallback
            logger.warning(
                f"Redis недоступен при инициализации Celery worker ({exc!s}). "
                "Продолжаем в режиме fallback (in-memory).",
            )
            # Создаем in-memory fallback напрямую
            from infra.redis.redis_client import _InMemoryRedis

            redis_client = _InMemoryRedis()

        postgres_pool = await init_postgres_pool(min_size=1, max_size=10, config=config_obj)
        await ensure_schema(pool=postgres_pool)

        logger.info("Celery pools initialized in worker process")
        return (postgres_pool, redis_client)


async def get_services_context(config_obj: Config | None = None) -> dict[str, object]:
    """Получает контекст сервисов для использования в Celery задачах.

    Инициализирует пулы подключений и создаёт экземпляры сервисов при первом вызове.
    Использует dependency injection вместо глобального состояния.

    Args:
        config_obj: Экземпляр Config. Если None, используется глобальный config.

    Returns:
        Словарь с сервисами:
        - bot: Экземпляр WednesdayBot
        - postgres_pool: Пул подключений PostgreSQL (для прямого использования в задачах)
        - redis_client: Redis-клиент (для прямого использования в задачах)
        - image_service: Экземпляр ImageService для генерации изображений
        - usage_tracker: Экземпляр UsageTracker для отслеживания использования
        - frog_processing: Экземпляр FrogProcessingService для обработки запросов /frog

    Raises:
        RuntimeError: Если не удалось инициализировать сервисы.
    """
    global _services_context  # noqa: PLW0603

    if config_obj is None:
        config_obj = config

    # Проверяем, инициализирован ли контекст (только чтение, без global)
    if _services_context is not None:
        return _services_context

    async with _init_lock:
        if _services_context is not None:
            return _services_context

        # Инициализируем пулы и получаем их явно (без использования приватных функций)
        postgres_pool, redis_client = await _ensure_pools_initialized(config_obj=config_obj)

        # Ленивый импорт для избежания циклических зависимостей
        from infra.container import build_bot

        # Convert to Config if needed
        if not isinstance(config_obj, Config):
            config_obj = Config()

        # Создаём сервисы через DI-контейнер (без зависимости от bot.services)
        from infra.container import (
            build_admin_notification_service,
            build_frog_processing_service,
            build_image_stack,
        )
        from infra.messaging.ptb import PTBMessagingService
        from infra.repos import AdminsRepo
        from infra.repos.usage_tracker import UsageTracker

        # Создаём image_service через DI-контейнер
        image_service = build_image_stack(
            config=config_obj,
            db_pool=postgres_pool,
            redis_client=redis_client,
        )

        # Создаём usage_tracker через DI
        usage_tracker = UsageTracker(
            pool=postgres_pool,
            monthly_quota=100,
            frog_threshold=70,
        )

        # Передаём пулы явно в build_bot (bot нужен для некоторых задач)
        bot = build_bot(
            config=config_obj,
            db_pool=postgres_pool,
            redis_client=redis_client,
        )

        # Создаём messaging service
        messaging_service = PTBMessagingService(bot=bot.application.bot)

        # Создаём admin notifier
        admins_repo = AdminsRepo(pool=postgres_pool)
        admin_notifier = build_admin_notification_service(
            messaging_service=messaging_service,
            admins_repo=admins_repo,
            logger=logger,
        )

        # Создаём frog processing service через DI (без зависимости от bot.services)
        frog_processing = build_frog_processing_service(
            image_service=image_service,
            messaging_service=messaging_service,
            usage_tracker=usage_tracker,
            admin_notifier=admin_notifier,
            logger=logger,
        )

        # Создаём cleanup service для graceful shutdown
        from infra.container import build_cleanup_service

        global _cleanup_service  # noqa: PLW0603
        _cleanup_service = build_cleanup_service(logger=logger)

        _services_context = {
            "bot": bot,
            "postgres_pool": postgres_pool,  # Добавляем в контекст
            "redis_client": redis_client,  # Добавляем в контекст
            "image_service": image_service,  # Добавляем в контекст
            "usage_tracker": usage_tracker,  # Добавляем в контекст
            "frog_processing": frog_processing,  # Добавляем в контекст
        }
        logger.info("Celery services context created in worker process")

    return _services_context


async def shutdown_services() -> None:
    """Graceful shutdown для async ресурсов.

    Закрывает все соединения при остановке worker через CleanupService:
    - ML-клиенты (ImageClientContainer, TextClientContainer) через aclose()
    - aiohttp sessions через закрытие клиентов
    - redis pool
    - postgres pool

    ⚠️ ВАЖНО: Вызывается автоматически через сигнал worker_shutdown
    """
    global _services_context, _cleanup_service  # noqa: PLW0603

    if _services_context is None:
        return

    logger.info("Shutting down Celery services...")

    try:
        # Используем CleanupService для закрытия всех ресурсов
        if _cleanup_service is not None:
            await _cleanup_service.cleanup_all()
        else:
            logger.warning("CleanupService not initialized, skipping cleanup")
    except Exception as e:
        logger.error(f"Error during Celery services shutdown: {e}")
    finally:
        _services_context = None
        _cleanup_service = None
        logger.info("Celery services shutdown complete")


# Регистрируем shutdown handler
@worker_shutdown.connect
def _on_worker_shutdown(sender: object | None = None, **kwargs: object) -> None:
    """Обработчик сигнала остановки worker для graceful shutdown.

    Вызывается автоматически при остановке Celery worker. Выполняет graceful
    shutdown всех async ресурсов:
    - ML-клиенты (ImageClientContainer, TextClientContainer) через aclose()
    - HTTP-сессии (aiohttp) через закрытие клиентов
    - Redis и Postgres пулы подключений

    Args:
        sender: Отправитель сигнала (обычно Celery app).
        **kwargs: Дополнительные аргументы сигнала.

    Note:
        Для celery[asyncio] worker_shutdown может быть вызван в контексте async,
        но сигнал сам по себе синхронный. Используем безопасный подход с проверкой
        наличия event loop.
    """
    try:
        # Пытаемся получить текущий event loop
        try:
            loop = asyncio.get_running_loop()
            # Если loop запущен, создаём задачу (для celery[asyncio])
            if not loop.is_closed():
                task = asyncio.create_task(shutdown_services())
                # Сохраняем ссылку на задачу, чтобы она не была удалена сборщиком мусора
                _ = task
            else:
                # Loop закрыт, создаём новый
                asyncio.run(shutdown_services())
        except RuntimeError:
            # Нет запущенного loop, создаём новый
            asyncio.run(shutdown_services())
    except Exception as e:
        logger.error(f"Ошибка при вызове shutdown в worker_shutdown handler: {e}")
