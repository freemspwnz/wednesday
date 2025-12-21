"""Application service для постановки задач генерации жабы в очередь.

Инкапсулирует логику взаимодействия с очередью задач, скрывая детали постановки задач
от handlers.
"""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.protocols import ILogger, ITaskQueue


class FrogRequestService(BaseService):
    """Application service для постановки задач генерации жабы в очередь.

    Предоставляет высокоуровневый интерфейс для постановки задач генерации,
    скрывая детали работы с очередью задач от handlers.
    """

    def __init__(self, task_queue: ITaskQueue, *, logger: ILogger) -> None:
        """Инициализирует FrogRequestService.

        Args:
            task_queue: Реализация ITaskQueue для отправки задач.
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self.task_queue = task_queue

    async def request_manual_frog(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None,
    ) -> None:
        """Ставит задачу генерации и отправки жабы в очередь.

        Args:
            chat_id: ID чата для отправки изображения.
            user_id: ID пользователя, запросившего генерацию (для логирования).
            status_message_id: ID статусного сообщения для удаления после отправки (опционально).

        Raises:
            Exception: При ошибке постановки задачи в очередь.
        """
        await self.task_queue.send_frog_manual_task(
            chat_id=chat_id,
            user_id=user_id,
            status_message_id=status_message_id,
        )
