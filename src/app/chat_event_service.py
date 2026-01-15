"""Application service для обработки событий чата.

Инкапсулирует логику обработки событий добавления/удаления бота из чатов,
соблюдая границы слоёв и централизуя обработку ошибок.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.chat_info_service import ChatInfoService
from shared.base.base_service import BaseService
from shared.base.exceptions import ServiceError
from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    from app.admin_command_service import AdminCommandService


class ChatEventService(BaseService):
    """Сервис для обработки событий чата.

    Инкапсулирует логику обработки событий добавления/удаления бота из чатов,
    централизуя обработку ошибок.
    """

    def __init__(
        self,
        *,
        admin_command_service: AdminCommandService,
        chat_info_service: ChatInfoService,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис обработки событий чата.

        Args:
            admin_command_service: Сервис для выполнения админских команд.
            chat_info_service: Сервис для получения информации о чатах.
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._admin_command = admin_command_service
        self._chat_info_service = chat_info_service

    async def handle_bot_added(
        self,
        chat_id: int,
    ) -> None:
        """Обрабатывает событие добавления бота в чат.

        Args:
            chat_id: ID чата, в который добавлен бот.

        Side Effects:
            - Добавляет чат в список рассылки через admin_command_service.
            - Логирует результат операции.
        """
        try:
            result = await self._admin_command.add_chat(chat_id, "Bot added to chat")
            if not result.success:
                self.logger.warning(f"Не удалось добавить чат {chat_id}: {result.message}")
        except ServiceError as e:
            self.logger.error(
                f"Ошибка сервиса при добавлении чата {chat_id}: {e}",
                exc_info=True,
            )
        except Exception as e:
            self.logger.error(
                f"Неожиданная ошибка при добавлении чата {chat_id}: {e}",
                exc_info=True,
            )

    async def handle_bot_removed(
        self,
        chat_id: int,
    ) -> None:
        """Обрабатывает событие удаления бота из чата.

        Args:
            chat_id: ID чата, из которого удалён бот.

        Side Effects:
            - Удаляет чат из списка рассылки через admin_command_service.
            - Логирует результат операции.
        """
        try:
            result = await self._admin_command.remove_chat(chat_id)
            if not result.success:
                self.logger.warning(f"Не удалось удалить чат {chat_id}: {result.message}")
        except ServiceError as e:
            self.logger.error(
                f"Ошибка сервиса при удалении чата {chat_id}: {e}",
                exc_info=True,
            )
        except Exception as e:
            self.logger.error(
                f"Неожиданная ошибка при удалении чата {chat_id}: {e}",
                exc_info=True,
            )
