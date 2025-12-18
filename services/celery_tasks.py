"""
Инициализация и управление сервисами для Celery задач.

Обеспечивает fork-safe инициализацию сервисов в Celery worker процессах.
Все async ресурсы создаются ПОСЛЕ fork, внутри задач.
"""

from __future__ import annotations

import asyncio

from celery.signals import worker_shutdown

from bot.wednesday_bot import WednesdayBot
from services.clients import get_image_client_container, get_text_client_container
from utils.config import config
from utils.logger import get_logger
from utils.postgres_client import close_postgres_pool, init_postgres_pool
from utils.postgres_schema import ensure_schema
from utils.redis_client import close_redis, init_redis_pool

logger = get_logger(__name__)


# Context для хранения инициализированных сервисов в worker процессе
_services_context: dict[str, object] | None = None
_init_lock = asyncio.Lock()


async def _ensure_pools_initialized() -> None:
    """Инициализирует пулы подключений Redis и Postgres.

    Инициализация происходит внутри задач, после fork worker процесса, что гарантирует:
    - Fork safety (соединения создаются после fork).
    - Отсутствие race conditions.

    Raises:
        RuntimeError: Если не удалось инициализировать пулы подключений.
    """
    # Проверяем, инициализирован ли контекст (только чтение, без global)
    if _services_context is not None:
        return

    async with _init_lock:
        if _services_context is not None:
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

        logger.info("Celery pools initialized in worker process")


async def get_services_context() -> dict[str, object]:
    """Получает контекст сервисов для использования в Celery задачах.

    Инициализирует пулы подключений и создаёт экземпляры сервисов при первом вызове.
    Использует dependency injection вместо глобального состояния.

    Returns:
        Словарь с сервисами:
        - bot: Экземпляр WednesdayBot

    Raises:
        RuntimeError: Если не удалось инициализировать сервисы.
    """
    global _services_context  # noqa: PLW0603

    await _ensure_pools_initialized()

    if _services_context is None:
        async with _init_lock:
            if _services_context is None:
                # Создаём экземпляры сервисов
                bot = WednesdayBot()

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
        # Закрываем ML-клиенты (контейнеры управляют HTTP-сессиями внутри)
        try:
            image_container = get_image_client_container()
            await image_container.aclose()
            logger.info("ImageClientContainer closed")
        except Exception as e:
            logger.warning(f"Error closing ImageClientContainer: {e}")

        try:
            text_container = get_text_client_container()
            await text_container.aclose()
            logger.info("TextClientContainer closed")
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
