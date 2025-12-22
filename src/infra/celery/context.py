"""
Инициализация и управление сервисами для Celery задач.

Обеспечивает fork-safe инициализацию сервисов в Celery worker процессах.
Все async ресурсы создаются ПОСЛЕ fork, внутри задач.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from celery.signals import worker_shutdown

from infra.clients import get_image_client_container, get_text_client_container
from infra.database.postgres_client import close_postgres_pool, init_postgres_pool
from infra.database.postgres_schema import ensure_schema
from infra.logging.logger import get_logger
from infra.redis.redis_client import close_redis, init_redis_pool
from shared.config_v2 import ConfigV2

# Создаём экземпляр ConfigV2 при импорте модуля
config: ConfigV2 = ConfigV2()

if TYPE_CHECKING:
    from bot.wednesday_bot import WednesdayBot

logger = get_logger(__name__)


# Context для хранения инициализированных сервисов в worker процессе
_services_context: dict[str, object] | None = None
_init_lock = asyncio.Lock()


async def _ensure_pools_initialized(config_obj: ConfigV2 | None = None) -> None:
    """Инициализирует пулы подключений Redis и Postgres.

    Инициализация происходит внутри задач, после fork worker процесса, что гарантирует:
    - Fork safety (соединения создаются после fork).
    - Отсутствие race conditions.

    Args:
        config_obj: Экземпляр ConfigV2. Если None, используется глобальный config.

    Raises:
        RuntimeError: Если не удалось инициализировать пулы подключений.
    """
    # Проверяем, инициализирован ли контекст (только чтение, без global)
    if _services_context is not None:
        return

    if config_obj is None:
        config_obj = config

    async with _init_lock:
        if _services_context is not None:
            return

        # Инициализируем Redis и Postgres (async)
        # ВАЖНО: это происходит ПОСЛЕ fork, в worker процессе
        if isinstance(config_obj, ConfigV2):
            if config_obj.redis.url:
                await init_redis_pool(url=config_obj.redis.url)
            else:
                await init_redis_pool(
                    host=config_obj.redis.host,
                    port=config_obj.redis.port,
                    db=config_obj.redis.db,
                    password=config_obj.redis.password,
                )
        elif config_obj.redis_url:
            await init_redis_pool(url=config_obj.redis_url)
        else:
            await init_redis_pool(
                host=config_obj.redis_host,
                port=config_obj.redis_port,
                db=config_obj.redis_db,
                password=config_obj.redis_password,
            )
        await init_postgres_pool(min_size=1, max_size=10, config=config_obj)
        await ensure_schema()

        logger.info("Celery pools initialized in worker process")


async def get_services_context(config_obj: ConfigV2 | None = None) -> dict[str, object]:
    """Получает контекст сервисов для использования в Celery задачах.

    Инициализирует пулы подключений и создаёт экземпляры сервисов при первом вызове.
    Использует dependency injection вместо глобального состояния.

    Args:
        config_obj: Экземпляр ConfigV2. Если None, используется глобальный config.

    Returns:
        Словарь с сервисами:
        - bot: Экземпляр WednesdayBot

    Raises:
        RuntimeError: Если не удалось инициализировать сервисы.
    """
    global _services_context  # noqa: PLW0603

    if config_obj is None:
        config_obj = config

    await _ensure_pools_initialized(config_obj=config_obj)

    if _services_context is None:
        async with _init_lock:
            if _services_context is None:
                # Ленивый импорт для избежания циклических зависимостей
                from infra.container import build_bot
                from infra.database.postgres_client import get_postgres_pool

                # Создаём экземпляры сервисов
                postgres_pool = get_postgres_pool()
                # Convert to ConfigV2 if needed
                if not isinstance(config_obj, ConfigV2):
                    config_obj = ConfigV2()
                bot = build_bot(config=config_obj, db_pool=postgres_pool)

                _services_context = {
                    "bot": bot,
                }
                logger.info("Celery services context created in worker process")

    return _services_context


async def shutdown_services() -> None:
    """Graceful shutdown для async ресурсов.

    Закрывает все соединения при остановке worker:
    - ML-клиенты (ImageClientContainer, TextClientContainer) через aclose()
    - aiohttp sessions через закрытие клиентов
    - redis pool
    - postgres pool

    ⚠️ ВАЖНО: Вызывается автоматически через сигнал worker_shutdown
    """
    global _services_context  # noqa: PLW0603

    if _services_context is None:
        return

    logger.info("Shutting down Celery services...")

    try:
        # Закрываем ресурсы через BotServices, если bot доступен
        bot = _services_context.get("bot")
        if bot is not None and hasattr(bot, "services") and hasattr(bot.services, "cleanup"):
            try:
                await bot.services.cleanup()
                logger.info("BotServices resources closed via cleanup()")
            except Exception as e:
                logger.warning(f"Error closing BotServices resources: {e}")
        else:
            # Fallback: закрываем контейнеры напрямую, если bot недоступен
            try:
                image_container = get_image_client_container()
                await image_container.aclose()
                logger.info("ImageClientContainer closed (fallback)")
            except Exception as e:
                logger.warning(f"Error closing ImageClientContainer: {e}")

            try:
                text_container = get_text_client_container()
                await text_container.aclose()
                logger.info("TextClientContainer closed (fallback)")
            except Exception as e:
                logger.warning(f"Error closing TextClientContainer: {e}")

        # Закрываем пулы подключений
        await close_postgres_pool()
        await close_redis()
    except Exception as e:
        logger.error(f"Error during Celery services shutdown: {e}")
    finally:
        _services_context = None
        logger.info("Celery services shutdown complete")


# Обратная совместимость: класс CeleryServices для существующего кода
class CeleryServices:
    """Класс для обратной совместимости (deprecated).

    Используйте функцию get_services_context() вместо этого класса.
    """

    @classmethod
    async def get_bot(cls) -> WednesdayBot:
        """Получает экземпляр WednesdayBot.

        Deprecated: используйте get_services_context()["bot"] вместо этого метода.

        Returns:
            Экземпляр WednesdayBot.

        Raises:
            RuntimeError: Если не удалось инициализировать WednesdayBot.
        """
        from bot.wednesday_bot import WednesdayBot

        context = await get_services_context()
        bot = context.get("bot")
        if not isinstance(bot, WednesdayBot):
            raise RuntimeError("Failed to initialize WednesdayBot")
        return bot

    @classmethod
    async def get_generator(cls) -> None:
        """DEPRECATED: генератор изображений больше не предоставляется напрямую.

        Deprecated: используйте get_services_context()["generator"] вместо этого метода.

        Returns:
            None.
        """
        await get_services_context()


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
