"""
Инициализация и управление сервисами для Celery задач.

Обеспечивает fork-safe инициализацию сервисов в Celery worker процессах.
Все async ресурсы создаются ПОСЛЕ fork, внутри задач.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypedDict, cast

import asyncpg
from celery.signals import worker_shutdown

from infra.database.postgres_client import PostgresPoolFactory
from infra.database.postgres_schema import ensure_schema
from infra.logging.logger import get_logger
from infra.redis.redis_client import RedisClientFactory
from shared.config import Config

if TYPE_CHECKING:
    from bot.wednesday_bot import WednesdayBot
    from infra.cleanup_service import CleanupService
    from infra.redis.redis_client import RedisClient
    from infra.repos.usage_tracker import UsageTracker

from shared.protocols import IFrogProcessingService, IImageService

logger = get_logger(__name__)


class ServicesContext(TypedDict, total=False):
    """Типизированный словарь контекста сервисов Celery.

    Определяет структуру контекста, возвращаемого get_services_context().
    Используется для типизации контекста сервисов в Celery задачах.

    Note:
        Все зависимости используют TYPE_CHECKING для избежания циклических зависимостей.
        total=False означает, что все поля опциональны (для совместимости с dict[str, object]).
        Используются протоколы вместо конкретных классов для соблюдения границ слоёв.
    """

    bot: WednesdayBot
    postgres_pool: asyncpg.Pool
    redis_client: RedisClient
    image_service: IImageService
    usage_tracker: UsageTracker
    frog_processing: IFrogProcessingService


# Context для хранения инициализированных сервисов в worker процессе
_services_context: dict[str, object] | None = None
_cleanup_service: CleanupService | None = None
_pool_factory: PostgresPoolFactory | None = None
_redis_factory: RedisClientFactory | None = None
_init_lock = asyncio.Lock()


def create_factories(config_obj: Config) -> tuple[PostgresPoolFactory, RedisClientFactory]:
    """Создаёт фабрики для Postgres и Redis с использованием конфигурации.

    Helper функция для явного создания фабрик в Celery задачах.
    Фабрики должны создаваться ПОСЛЕ fork worker процесса для fork-safety.

    Args:
        config_obj: Экземпляр Config для создания фабрик.

    Returns:
        Кортеж (pool_factory, redis_factory) с созданными фабриками.
    """
    pool_factory = PostgresPoolFactory(config=config_obj)
    redis_factory = RedisClientFactory(config=config_obj)
    return (pool_factory, redis_factory)


async def _get_redis_client(
    redis_factory: RedisClientFactory,
    config_obj: Config,
) -> RedisClient:
    """Создаёт Redis клиент через фабрику с использованием конфигурации.

    Args:
        redis_factory: Фабрика для создания Redis клиента.
        config_obj: Экземпляр Config для получения параметров подключения.

    Returns:
        Инициализированный Redis клиент.

    Raises:
        Exception: Если не удалось создать Redis клиент.
    """
    if isinstance(config_obj, Config):
        if config_obj.redis.url:
            return await redis_factory.get_client(url=config_obj.redis.url)
        return await redis_factory.get_client(
            host=config_obj.redis.host,
            port=config_obj.redis.port,
            db=config_obj.redis.db,
            password=config_obj.redis.password,
        )
    if config_obj.redis_url:
        return await redis_factory.get_client(url=config_obj.redis_url)
    return await redis_factory.get_client(
        host=config_obj.redis_host,
        port=config_obj.redis_port,
        db=config_obj.redis_db,
        password=config_obj.redis_password,
    )


async def _ensure_pools_initialized(
    pool_factory: PostgresPoolFactory,
    redis_factory: RedisClientFactory,
    config_obj: Config,
) -> tuple[asyncpg.Pool, RedisClient]:
    """Инициализирует пулы подключений Redis и Postgres.

    Инициализация происходит внутри задач, после fork worker процесса, что гарантирует:
    - Fork safety (соединения создаются после fork).
    - Отсутствие race conditions.

    Args:
        pool_factory: Фабрика для создания Postgres пула (обязательна).
        redis_factory: Фабрика для создания Redis клиента (обязательна).
        config_obj: Экземпляр Config (обязателен).

    Returns:
        Кортеж (postgres_pool, redis_client) с инициализированными пулами.

    Raises:
        RuntimeError: Если не удалось инициализировать пулы подключений.
    """
    async with _init_lock:
        # Инициализируем Redis и Postgres (async)
        # ВАЖНО: это происходит ПОСЛЕ fork, в worker процессе
        global _pool_factory, _redis_factory  # noqa: PLW0603

        _pool_factory = pool_factory
        _redis_factory = redis_factory

        redis_client: RedisClient
        try:
            redis_client = await _get_redis_client(redis_factory, config_obj)
        except Exception as exc:
            # Redis критичен для Celery worker — пробрасываем ошибку
            logger.error(
                f"Redis недоступен при инициализации Celery worker: {exc!s}",
                event="celery_redis_unavailable",
                status="error",
            )
            raise

        postgres_pool = await pool_factory.get_pool(min_size=1, max_size=10)
        await ensure_schema(pool=postgres_pool)

        logger.info(
            "Пулы Celery (PostgreSQL и Redis) инициализированы в worker-процессе",
            event="celery_pools_initialized",
            status="success",
        )
        return (postgres_pool, redis_client)


async def get_services_context(
    pool_factory: PostgresPoolFactory,
    redis_factory: RedisClientFactory,
    config_obj: Config,
) -> ServicesContext:
    """Получает контекст сервисов для использования в Celery задачах.

    Инициализирует пулы подключений и создаёт экземпляры сервисов при первом вызове.
    Использует dependency injection вместо глобального состояния.

    Args:
        pool_factory: Фабрика для создания Postgres пула (обязательна).
        redis_factory: Фабрика для создания Redis клиента (обязательна).
        config_obj: Экземпляр Config (обязателен).

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

    # Проверяем, инициализирован ли контекст (только чтение, без global)
    if _services_context is not None:
        return cast("ServicesContext", _services_context)

    async with _init_lock:
        if _services_context is not None:
            return cast("ServicesContext", _services_context)

        # Инициализируем пулы и получаем их явно (без использования приватных функций)
        postgres_pool, redis_client = await _ensure_pools_initialized(
            pool_factory=pool_factory,
            redis_factory=redis_factory,
            config_obj=config_obj,
        )

        # Ленивый импорт для избежания циклических зависимостей
        # Создаём сервисы через DI-контейнер (без зависимости от bot.services)
        from infra.container import (
            build_admin_notification_service,
            build_bot,
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
        from shared.config import TelegramConfig

        telegram_config = TelegramConfig()
        admins_repo = AdminsRepo(pool=postgres_pool, admin_chat_id=telegram_config.admin_chat_id)
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
        _cleanup_service = build_cleanup_service(
            logger=logger,
            pool_factory=_pool_factory,
            redis_factory=_redis_factory,
        )

        _services_context = {
            "bot": bot,
            "postgres_pool": postgres_pool,  # Добавляем в контекст
            "redis_client": redis_client,  # Добавляем в контекст
            "image_service": image_service,  # Добавляем в контекст
            "usage_tracker": usage_tracker,  # Добавляем в контекст
            "frog_processing": frog_processing,  # Добавляем в контекст
        }
        logger.info(
            "Контекст сервисов Celery создан в worker-процессе",
            event="celery_services_context_created",
            status="success",
        )

    return cast("ServicesContext", _services_context)


async def shutdown_services() -> None:
    """Graceful shutdown для async ресурсов.

    Закрывает все соединения при остановке worker через CleanupService:
    - ML-клиенты (ImageClientContainer, TextClientContainer) через aclose()
    - aiohttp sessions через закрытие клиентов
    - redis pool через фабрику
    - postgres pool через фабрику

    ⚠️ ВАЖНО: Вызывается автоматически через сигнал worker_shutdown
    """
    global _services_context, _cleanup_service, _pool_factory, _redis_factory  # noqa: PLW0603

    if _services_context is None:
        return

    logger.info(
        "Начинаю graceful shutdown сервисов Celery",
        event="celery_shutdown_started",
        status="started",
    )

    try:
        # Используем CleanupService для закрытия всех ресурсов
        if _cleanup_service is not None:
            await _cleanup_service.cleanup_all()
        else:
            logger.warning(
                "CleanupService не инициализирован, пропускаю этап очистки ресурсов",
                event="celery_cleanup_service_missing",
                status="warning",
            )

        # Закрываем фабрики пулов
        if _pool_factory is not None:
            try:
                await _pool_factory.close()
                logger.info("Postgres pool закрыт через фабрику в Celery worker")
            except Exception as e:
                logger.warning(f"Ошибка при закрытии Postgres pool: {e}")

        if _redis_factory is not None:
            try:
                await _redis_factory.close()
                logger.info("Redis клиент закрыт через фабрику в Celery worker")
            except Exception as e:
                logger.warning(f"Ошибка при закрытии Redis клиента: {e}")
    except Exception as e:
        logger.error(
            f"Ошибка во время graceful shutdown сервисов Celery: {e}",
            event="celery_shutdown_error",
            status="error",
            error_type=type(e).__name__,
            error_message=str(e),
        )
    finally:
        _services_context = None
        _cleanup_service = None
        _pool_factory = None
        _redis_factory = None
        logger.info(
            "Graceful shutdown сервисов Celery завершён",
            event="celery_shutdown_completed",
            status="success",
        )


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
