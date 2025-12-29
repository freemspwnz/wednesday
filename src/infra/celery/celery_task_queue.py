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
            self.celery_app.send_task(
                CeleryTaskNames.WEDNESDAY_SEND_FROG_MANUAL,
                args=[chat_id, user_id, status_message_id, idempotency_key],
            )
            self.logger.info(f"Задача send_frog_manual поставлена в очередь для пользователя {user_id}")
        except Exception as e:
            self.logger.error(f"Не удалось поставить задачу в очередь Celery: {e}")
            raise
