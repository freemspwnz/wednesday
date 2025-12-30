"""
Инициализация и управление ресурсами для Celery задач с asyncio pool.

Обеспечивает singleton Container и управление жизненным циклом ресурсов
через contextlib.AsyncExitStack для корректной очистки при 1 ГБ RAM.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

import aiohttp
from telegram import Bot

from infra.database.postgres_client import PostgresPoolFactory
from infra.database.postgres_schema import ensure_schema
from infra.logging.logger import get_logger
from infra.redis.redis_client import RedisClientFactory
from shared.config import Config

if TYPE_CHECKING:
    from infra.new_container import Container

logger = get_logger("celery.worker_context")


class WorkerContext:
    """Контекст для управления жизненным циклом ресурсов воркера.

    Гарантирует наличие только одного экземпляра Container в worker процессе.
    Использует AsyncExitStack для автоматической очистки ресурсов при shutdown.
    """

    def __init__(self) -> None:
        """Инициализирует WorkerContext."""
        self._container: Container | None = None
        self._exit_stack = AsyncExitStack()
        self._init_lock = asyncio.Lock()
        self._config: Config | None = None

    async def get_container(self) -> Container:
        """Получает или создаёт Container с инициализированными ресурсами.

        Реализует ленивую инициализацию: ресурсы создаются только при первом вызове.
        Использует AsyncExitStack для автоматического управления жизненным циклом.

        Returns:
            Экземпляр Container с инициализированными ресурсами.

        Raises:
            RuntimeError: Если не удалось инициализировать ресурсы.
        """
        if self._container is not None:
            return self._container

        async with self._init_lock:
            # Double-check после получения lock
            if self._container is not None:
                return self._container

            logger.info(
                "Начало инициализации ресурсов воркера",
                event="worker_context_init_start",
                status="started",
            )

            try:
                # Создаём Config
                self._config = Config()

                # Создаём фабрики
                pool_factory = PostgresPoolFactory(config=self._config)
                redis_factory = RedisClientFactory(config=self._config)

                # Инициализируем ресурсы
                postgres_pool = await pool_factory.get_pool(min_size=1, max_size=10)
                await ensure_schema(pool=postgres_pool)

                # Регистрируем callback для закрытия Postgres pool
                self._exit_stack.push_async_callback(postgres_pool.close)
                logger.debug("Postgres pool зарегистрирован для закрытия через AsyncExitStack")

                redis_client = await redis_factory.get_client()

                # Регистрируем callback для закрытия Redis client
                # Используем aclose() если доступен, иначе close()
                if hasattr(redis_client, "aclose") and asyncio.iscoroutinefunction(redis_client.aclose):
                    self._exit_stack.push_async_callback(redis_client.aclose)
                else:
                    self._exit_stack.push_async_callback(redis_client.close)
                logger.debug("Redis client зарегистрирован для закрытия через AsyncExitStack")

                # Создаём HTTP сессию через AsyncExitStack (создается на лету)
                http_session = await self._exit_stack.enter_async_context(aiohttp.ClientSession())

                # Создаём Bot instance
                bot_token = self._config.telegram.bot_token
                if not bot_token:
                    raise ValueError("TELEGRAM_BOT_TOKEN должен быть установлен")
                bot_instance = Bot(token=bot_token)

                # Создаём Metrics
                from infra.metrics.metrics import Metrics

                metrics = Metrics(
                    pool=postgres_pool,
                    logger=logger,
                    redis_factory=redis_factory,
                )

                # Создаём TaskQueue
                from infra.celery.celery_task_queue import CeleryTaskQueue

                task_queue = CeleryTaskQueue()

                # Создаём Container
                from infra.new_container import Container

                self._container = Container(
                    config=self._config,
                    logger=logger,
                    db_pool=postgres_pool,
                    redis_client=redis_client,
                    bot_client=bot_instance,
                    metrics_service=metrics,
                    task_queue=task_queue,
                    http_session=http_session,
                )

                # Вызываем build_bot_services для инициализации сервисов
                self._container.build_bot_services()

                logger.info(
                    "Ресурсы воркера успешно инициализированы",
                    event="worker_context_init_success",
                    status="ok",
                )

                return self._container

            except Exception as e:
                logger.error(
                    f"Ошибка при инициализации ресурсов воркера: {e}",
                    event="worker_context_init_error",
                    status="error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                # Закрываем ресурсы при ошибке
                await self.close()
                raise RuntimeError(f"Не удалось инициализировать ресурсы воркера: {e}") from e

    async def close(self) -> None:
        """Закрывает все ресурсы через AsyncExitStack.

        Вызывается автоматически при shutdown worker процесса.
        AsyncExitStack автоматически закроет все ресурсы в обратном порядке (LIFO):
        1. HTTP сессия (aiohttp.ClientSession)
        2. Redis client (через aclose/close callback)
        3. Postgres pool (через close callback)

        Порядок закрытия предотвращает ситуацию, когда сервис пытается что-то
        записать в уже закрытую базу при выключении.

        Гарантирует корректное закрытие всех соединений для экономии RAM.
        """
        if self._container is None:
            logger.debug("Container не инициализирован, пропускаем закрытие ресурсов")
            return

        logger.info(
            "Начало закрытия ресурсов воркера",
            event="worker_context_close_start",
            status="started",
        )

        try:
            # AsyncExitStack автоматически закроет все ресурсы в обратном порядке
            # Это обеспечивает поведение, идентичное async with
            await self._exit_stack.aclose()

            logger.info(
                "Ресурсы воркера успешно закрыты через AsyncExitStack (HTTP сессия, Redis, Postgres)",
                event="worker_context_close_success",
                status="ok",
            )
        except Exception as e:
            logger.error(
                f"Ошибка при закрытии ресурсов воркера: {e}",
                event="worker_context_close_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
        finally:
            self._container = None
            self._config = None


# Глобальный экземпляр WorkerContext
worker_ctx = WorkerContext()
