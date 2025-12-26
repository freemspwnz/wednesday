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
    from infra.celery.cleanup_service import CleanupService
    from infra.redis.redis_client import RedisClient
    from infra.repos.usage_tracker import UsageTracker

from shared.protocols import (
    IDataCleanupService,
    IFrogProcessingService,
    IIdempotencyService,
    IImageService,
)

logger = get_logger(__name__)


class ServicesContext(TypedDict, total=False):
    """Типизированный словарь контекста сервисов Celery.

    Определяет структуру контекста, возвращаемого get_services_context().
    Используется для типизации контекста сервисов в Celery задачах.

    Note:
        Все зависимости используют TYPE_CHECKING для избежания циклических зависимостей.
        total=False означает, что все поля опциональны (для совместимости с dict[str, object]).
        Используются протоколы вместо конкретных классов для соблюдения границ слоёв.

        ⚠️ ВАЖНО: Пулы БД (postgres_pool, redis_client) НЕ включены в контекст,
        так как все операции с БД должны идти через сервисы и репозитории.
        Пулы используются только для создания сервисов через DI (fork-safe).
    """

    bot: WednesdayBot
    image_service: IImageService
    usage_tracker: UsageTracker
    frog_processing: IFrogProcessingService
    data_cleanup_service: IDataCleanupService
    idempotency_service: IIdempotencyService


# Context для хранения инициализированных сервисов в worker процессе
_services_context: dict[str, object] | None = None
_cleanup_service: CleanupService | None = None
_pool_factory: PostgresPoolFactory | None = None
_redis_factory: RedisClientFactory | None = None
_worker_pool_factory: PostgresPoolFactory | None = None
_worker_redis_factory: RedisClientFactory | None = None
_worker_config: Config | None = None
_shutdown_task: asyncio.Task[None] | None = None

_init_lock: asyncio.Lock | None = None
_factories_lock: asyncio.Lock | None = None


def _get_init_lock() -> asyncio.Lock:
    """Получает lock для инициализации контекста (создаётся лениво в текущем event loop).

    Для celery[asyncio] locks должны создаваться в том же event loop, где используются.
    """
    global _init_lock  # noqa: PLW0603
    if _init_lock is None:
        _init_lock = asyncio.Lock()
    return _init_lock


def _get_worker_factories_lock() -> asyncio.Lock:
    """Получает lock для фабрик worker (создаётся лениво в текущем event loop).

    Для celery[asyncio] locks должны создаваться в том же event loop, где используются.
    """
    global _factories_lock  # noqa: PLW0603
    if _factories_lock is None:
        _factories_lock = asyncio.Lock()
    return _factories_lock


async def get_or_create_worker_factories(
    config: Config | None = None,
) -> tuple[PostgresPoolFactory, RedisClientFactory, Config]:
    """Получает или создаёт фабрики для worker процесса (кэширует).

    Фабрики создаются один раз на worker процесс и переиспользуются
    между задачами. Это безопасно, так как каждая задача выполняется
    в том же worker процессе после fork.

    ⚠️ ВАЖНО: Фабрики используются ТОЛЬКО для создания пулов.
    После создания пулов через factory.get_pool() / factory.get_client(),
    пулы передаются в build_celery_services_context(), которая создаёт сервисы.
    Сервисы получают пулы через Dependency Injection, а не фабрики.

    Эта функция должна вызываться в Celery задачах для получения фабрик,
    которые затем передаются в get_services_context().

    Args:
        config: Экземпляр Config для создания фабрик. Если None, создаётся новый.

    Returns:
        Кортеж (pool_factory, redis_factory, config) с кэшированными фабриками.
    """
    global _worker_pool_factory, _worker_redis_factory, _worker_config  # noqa: PLW0603

    if config is None:
        config = Config()

    async with _get_worker_factories_lock():
        if _worker_pool_factory is None or _worker_redis_factory is None:
            _worker_config = config or Config()
            _worker_pool_factory = PostgresPoolFactory(config=_worker_config)
            _worker_redis_factory = RedisClientFactory(config=_worker_config)
            logger.info("Фабрики инициализированы в asyncio воркере")

        # Гарантируем, что все значения не None (явная проверка вместо assert для работы с -O)
        if _worker_config is None or _worker_pool_factory is None or _worker_redis_factory is None:
            raise RuntimeError("Worker factories and config must be set after factory creation")
        return _worker_pool_factory, _worker_redis_factory, _worker_config


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
    async with _get_init_lock():
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
    Использует dependency injection через build_celery_services_context() из container.py.

    ⚠️ ВАЖНО: Архитектура использования фабрик и пулов:
    1. Фабрики (pool_factory, redis_factory) используются ТОЛЬКО для создания пулов
    2. Пулы создаются ПОСЛЕ fork worker процесса (для fork safety)
    3. Созданные пулы передаются в build_celery_services_context(), которая создаёт сервисы
    4. Сервисы получают пулы через Dependency Injection, а не фабрики
    5. Фабрики сохраняются для cleanup service, который закрывает пулы при shutdown

    Фабрики должны быть переданы явно - это соблюдает принцип DI.
    Для получения фабрик используйте get_or_create_worker_factories().

    Args:
        pool_factory: Фабрика для создания Postgres пула (обязательна).
        redis_factory: Фабрика для создания Redis клиента (обязательна).
        config_obj: Экземпляр Config (обязателен).

    Returns:
        Словарь с сервисами:
        - bot: Экземпляр WednesdayBot
        - image_service: Экземпляр ImageService для генерации изображений
        - usage_tracker: Экземпляр UsageTracker для отслеживания использования
        - frog_processing: Экземпляр FrogProcessingService для обработки запросов /frog
        - data_cleanup_service: Экземпляр DataCleanupService для очистки данных
        - idempotency_service: Экземпляр IdempotencyService для идемпотентности

        ⚠️ ВАЖНО: postgres_pool и redis_client НЕ включены в контекст.
        Все операции с БД должны выполняться через сервисы и репозитории.
        Пулы используются только для создания сервисов через DI (fork-safe).

    Raises:
        RuntimeError: Если не удалось инициализировать сервисы.
    """
    global _services_context  # noqa: PLW0603

    # Проверяем, инициализирован ли контекст (только чтение, без global)
    if _services_context is not None:
        return cast("ServicesContext", _services_context)

    async with _get_init_lock():
        if _services_context is not None:
            return cast("ServicesContext", _services_context)

        # Сохраняем фабрики для cleanup
        global _pool_factory, _redis_factory  # noqa: PLW0603
        _pool_factory = pool_factory
        _redis_factory = redis_factory

        # Инициализируем пулы
        postgres_pool, redis_client = await _ensure_pools_initialized(
            pool_factory=pool_factory,
            redis_factory=redis_factory,
            config_obj=config_obj,
        )

        # Создаём сервисы через DI-контейнер (единый стиль с container.py)
        from infra.container import build_celery_services_context

        _services_context = build_celery_services_context(
            config=config_obj,
            db_pool=postgres_pool,
            redis_client=redis_client,
        )

        # Создаём cleanup service для graceful shutdown
        from infra.container import build_cleanup_service

        global _cleanup_service  # noqa: PLW0603
        _cleanup_service = build_cleanup_service(
            logger=logger,
            pool_factory=pool_factory,
            redis_factory=redis_factory,
        )

        logger.info(
            "Контекст сервисов Celery создан в worker-процессе",
            event="celery_services_context_created",
            status="success",
        )

    return cast("ServicesContext", _services_context)


async def shutdown_services() -> None:
    """Graceful shutdown для async ресурсов.

    Закрывает все соединения при остановке worker через CleanupService.
    Детали закрытия (ML-клиенты, Redis, Postgres) инкапсулированы в CleanupService.

    ⚠️ ВАЖНО: Вызывается автоматически через сигнал worker_shutdown.
    """
    global _services_context, _cleanup_service, _pool_factory, _redis_factory  # noqa: PLW0603
    global _worker_pool_factory, _worker_redis_factory, _worker_config  # noqa: PLW0603

    if _services_context is None and _cleanup_service is None:
        return

    logger.info(
        "Начинаю graceful shutdown сервисов Celery",
        event="celery_shutdown_started",
        status="started",
    )

    try:
        if _cleanup_service is not None:
            # CleanupService сам закроет всё: и ML-клиентов, и пулы через фабрики
            await _cleanup_service.cleanup_all()
        else:
            logger.warning(
                "CleanupService не инициализирован, глубокая очистка ресурсов невозможна",
                event="celery_cleanup_service_missing",
                status="warning",
            )
    except Exception as e:
        logger.error(
            f"Критическая ошибка во время cleanup_all: {e}",
            event="celery_shutdown_error",
            status="error",
            error_type=type(e).__name__,
            error_message=str(e),
        )
    finally:
        # Обнуляем все глобальные ссылки, чтобы избежать утечек памяти
        _services_context = None
        _cleanup_service = None
        _pool_factory = None
        _redis_factory = None
        _worker_pool_factory = None
        _worker_redis_factory = None
        _worker_config = None

        logger.info(
            "Graceful shutdown сервисов Celery завершён",
            event="celery_shutdown_completed",
            status="success",
        )


# Регистрируем shutdown handler
@worker_shutdown.connect
def _on_worker_shutdown(sender: object | None = None, **kwargs: object) -> None:
    """Обработчик остановки. Гарантирует выполнение shutdown_services.

    Для celery[asyncio] всегда есть running event loop, поэтому используем create_task().
    asyncio.run() не может быть вызван из running loop и вызовет RuntimeError.
    """
    global _shutdown_task  # noqa: PLW0603

    try:
        # Для celery[asyncio] всегда есть running event loop
        loop = asyncio.get_running_loop()
        if not loop.is_closed():
            # Создаём задачу для graceful shutdown
            _shutdown_task = loop.create_task(shutdown_services())
            # Сохраняем ссылку в глобальной переменной, чтобы задача не была удалена сборщиком мусора
        else:
            logger.warning(
                "Event loop is closed, cannot perform graceful shutdown",
                event="celery_shutdown_loop_closed",
                status="warning",
            )
    except RuntimeError:
        # Нет running loop - это не должно происходить в asyncio pool
        logger.warning(
            "No running event loop, cannot perform graceful shutdown",
            event="celery_shutdown_no_loop",
            status="warning",
        )
    except Exception as e:
        logger.error(
            f"Ошибка при вызове shutdown в worker_shutdown handler: {e}",
            event="celery_shutdown_handler_error",
            status="error",
            error_type=type(e).__name__,
            error_message=str(e),
        )
