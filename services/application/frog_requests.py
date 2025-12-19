"""Application service для постановки задач генерации жабы в очередь Celery.

Инкапсулирует логику взаимодействия с Celery, скрывая детали постановки задач
от handlers.
"""

from __future__ import annotations

from services.base.base_service import BaseService
from services.infrastructure.celery import celery_app
from services.infrastructure.celery.task_names import CeleryTaskNames


class FrogRequestService(BaseService):
    """Application service для постановки задач генерации жабы в очередь Celery.

    Предоставляет высокоуровневый интерфейс для постановки задач генерации,
    скрывая детали работы с Celery от handlers.
    """

    async def request_manual_frog(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None,
    ) -> None:
        """Ставит задачу генерации и отправки жабы в очередь Celery.

        Args:
            chat_id: ID чата для отправки изображения.
            user_id: ID пользователя, запросившего генерацию (для логирования).
            status_message_id: ID статусного сообщения для удаления после отправки (опционально).

        Raises:
            Exception: При ошибке постановки задачи в очередь Celery.
        """
        try:
            celery_app.send_task(
                CeleryTaskNames.WEDNESDAY_SEND_FROG_MANUAL,
                args=[chat_id, user_id, status_message_id],
            )
            self.logger.info(f"Задача send_frog_manual поставлена в очередь для пользователя {user_id}")
        except Exception as e:
            self.logger.error(f"Не удалось поставить задачу в очередь Celery: {e}")
            raise
