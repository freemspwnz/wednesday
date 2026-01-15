"""Application service для обработки команды /frog.

Инкапсулирует всю бизнес-логику команды /frog:
- Проверка rate limits
- Проверка месячных лимитов
- Постановка задачи в очередь
- Форматирование сообщений
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from shared.base.base_service import BaseService
from shared.protocols.infrastructure import ILogger
from shared.protocols.queues import ITaskQueue

if TYPE_CHECKING:
    from app.admin_access_service import AdminAccessService
    from app.bot_notification_builders import BotNotificationBuilders
    from app.frog_limit_service import FrogRateLimiterService


@dataclass
class FrogCommandResult:
    """Результат обработки команды /frog."""

    success: bool
    status_message: str | None = None
    error_message: str | None = None
    should_delete_status: bool = False


class FrogCommandService(BaseService):
    """Сервис для обработки команды /frog.

    Инкапсулирует всю бизнес-логику команды /frog:
    - Проверка rate limits
    - Проверка месячных лимитов
    - Постановка задачи в очередь
    - Форматирование сообщений
    """

    def __init__(
        self,
        *,
        frog_rate_limiter: FrogRateLimiterService,
        admin_access_service: AdminAccessService,
        task_queue: ITaskQueue,
        notification_builders: BotNotificationBuilders,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис обработки команды /frog.

        Args:
            frog_rate_limiter: Сервис проверки rate limits.
            admin_access_service: Сервис проверки прав администратора.
            task_queue: Очередь задач для постановки генерации.
            notification_builders: Билдеры для форматирования сообщений.
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._frog_rate_limiter = frog_rate_limiter
        self._admin_access = admin_access_service
        self._task_queue = task_queue
        self._notification_builders = notification_builders

    async def check_frog_command_allowed(
        self,
        user_id: int,
    ) -> FrogCommandResult:
        """Проверяет, разрешена ли команда /frog для пользователя.

        Args:
            user_id: ID пользователя.

        Returns:
            FrogCommandResult с результатом проверки.
            Если success=True, status_message содержит текст для отправки.
            Если success=False, error_message содержит текст ошибки.
        """
        # Проверка прав администратора
        is_admin = await self._admin_access.is_admin(user_id)

        # Проверка rate limit
        is_allowed, rate_limit_message = await self._frog_rate_limiter.check_and_consume(
            user_id=user_id,
            is_admin=is_admin,
        )
        if not is_allowed:
            error_message = self._notification_builders.format_rate_limit_error(rate_limit_message)
            return FrogCommandResult(
                success=False,
                error_message=error_message,
            )

        # Проверка месячного лимита
        can_generate, limit_message = await self._frog_rate_limiter.check_generation_allowed()
        if not can_generate:
            error_message = self._notification_builders.format_generation_limit_error(limit_message)
            return FrogCommandResult(
                success=False,
                error_message=error_message,
            )

        # Все проверки пройдены
        status_text = self._notification_builders.get_frog_generation_status_message()
        return FrogCommandResult(
            success=True,
            status_message=status_text,
        )

    async def enqueue_frog_generation(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None = None,
    ) -> FrogCommandResult:
        """Ставит задачу генерации жабы в очередь.

        Args:
            chat_id: ID чата.
            user_id: ID пользователя.
            status_message_id: ID статусного сообщения для удаления после отправки (опционально).

        Returns:
            FrogCommandResult с результатом постановки задачи.
        """
        try:
            await self._task_queue.send_frog_manual_task(
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message_id,
            )
            return FrogCommandResult(
                success=True,
            )
        except Exception as e:
            self.logger.error(
                f"Не удалось поставить задачу в очередь Celery: {e}",
                event="frog_command_queue_error",
                status="error",
                user_id=user_id,
                chat_id=chat_id,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            error_message = self._notification_builders.get_frog_queue_error_message()
            return FrogCommandResult(
                success=False,
                error_message=error_message,
                should_delete_status=True,
            )
