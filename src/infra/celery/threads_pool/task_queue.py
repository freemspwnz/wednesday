"""Реализация ITaskQueue через Celery."""

from __future__ import annotations

from typing import TYPE_CHECKING

from infra.celery.app import celery_app
from infra.celery.task_names import CeleryTaskNames
from infra.logging.logger import get_logger

if TYPE_CHECKING:
    from celery import Celery


class CeleryTaskQueue:
    """Реализация ITaskQueue через Celery.

    Инкапсулирует детали работы с Celery для отправки задач генерации жабы.
    """

    def __init__(self, celery_app_instance: Celery = celery_app) -> None:
        """Инициализирует CeleryTaskQueue.

        Args:
            celery_app_instance: Экземпляр Celery app. По умолчанию использует
                глобальный celery_app из infrastructure.celery.
        """
        self.celery_app = celery_app_instance
        self.logger = get_logger(__name__)

    async def send_frog_manual_task(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None,
        idempotency_key: str | None = None,
    ) -> None:
        """Ставит задачу генерации и отправки жабы в очередь Celery.

        Args:
            chat_id: ID чата для отправки изображения.
            user_id: ID пользователя, запросившего генерацию (для логирования).
            status_message_id: ID статусного сообщения для удаления после отправки (опционально).
            idempotency_key: Ключ идемпотентности для предотвращения дубликатов (опционально).
                Если не указан, будет сгенерирован автоматически в задаче.

        Raises:
            Exception: При ошибке постановки задачи в очередь Celery.
        """
        try:
            # Для celery[asyncio] send_task() можно вызывать напрямую, так как есть event loop
            # В asyncio pool синхронные вызовы не блокируют event loop
            self.celery_app.send_task(
                CeleryTaskNames.WEDNESDAY_SEND_FROG_MANUAL,
                args=[chat_id, user_id, status_message_id, idempotency_key],
            )
            self.logger.info(f"Задача send_frog_manual поставлена в очередь для пользователя {user_id}")
        except Exception as e:
            self.logger.error(f"Не удалось поставить задачу в очередь Celery: {e}")
            raise

    async def send_new_frog_task(
        self,
        slot_time: str | None = None,
    ) -> None:
        """Ставит новую задачу отправки жабы по расписанию в очередь Celery.

        Использует новую реализацию через WorkerContext с asyncio pool.

        Args:
            slot_time: Опциональное время слота в формате "HH:MM" для идентификации отправки.
                Если None, определяется автоматически в задаче.

        Raises:
            Exception: При ошибке постановки задачи в очередь Celery.
        """
        try:
            # Для celery[asyncio] send_task() можно вызывать напрямую, так как есть event loop
            # В asyncio pool синхронные вызовы не блокируют event loop
            self.celery_app.send_task(
                CeleryTaskNames.NEW_SEND_FROG,
                args=[slot_time],
            )
            self.logger.info(f"Задача new_send_frog поставлена в очередь (slot_time={slot_time or 'auto'})")
        except Exception as e:
            self.logger.error(f"Не удалось поставить задачу new_send_frog в очередь Celery: {e}")
            raise

    async def send_new_generate_image_task(
        self,
        prompt: str,
    ) -> None:
        """Ставит новую задачу генерации изображения в очередь Celery.

        Использует новую реализацию через WorkerContext с asyncio pool.

        Args:
            prompt: Промпт для генерации изображения.

        Raises:
            Exception: При ошибке постановки задачи в очередь Celery.
        """
        try:
            # Для celery[asyncio] send_task() можно вызывать напрямую, так как есть event loop
            # В asyncio pool синхронные вызовы не блокируют event loop
            self.celery_app.send_task(
                CeleryTaskNames.NEW_GENERATE_IMAGE,
                args=[prompt],
            )
            self.logger.info(f"Задача new_generate_image поставлена в очередь (prompt={prompt[:50]}...)")
        except Exception as e:
            self.logger.error(f"Не удалось поставить задачу new_generate_image в очередь Celery: {e}")
            raise

    async def send_new_daily_cleanup_task(self) -> None:
        """Ставит новую задачу ежедневной очистки в очередь Celery.

        Использует новую реализацию через WorkerContext с asyncio pool.

        Raises:
            Exception: При ошибке постановки задачи в очередь Celery.
        """
        try:
            # Для celery[asyncio] send_task() можно вызывать напрямую, так как есть event loop
            # В asyncio pool синхронные вызовы не блокируют event loop
            self.celery_app.send_task(
                CeleryTaskNames.NEW_DAILY_CLEANUP,
                args=[],
            )
            self.logger.info("Задача new_daily_cleanup поставлена в очередь")
        except Exception as e:
            self.logger.error(f"Не удалось поставить задачу new_daily_cleanup в очередь Celery: {e}")
            raise
