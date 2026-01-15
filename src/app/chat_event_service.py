"""Application service для обработки событий чата.

Инкапсулирует логику обработки событий добавления/удаления бота из чатов,
соблюдая границы слоёв и централизуя обработку ошибок.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.chat_info_service import ChatInfoService
from shared.base.base_service import BaseService
from shared.base.exceptions import ServiceError
from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    from telegram import Update

    from app.admin_command_service import AdminCommandService
    from shared.protocols.messaging import IMessagingService


@dataclass
class BotStatusChange:
    """Результат определения изменения статуса бота в чате."""

    was_added: bool
    was_removed: bool
    old_status: str | None
    new_status: str | None


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
        messaging_service: IMessagingService | None = None,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис обработки событий чата.

        Args:
            admin_command_service: Сервис для выполнения админских команд.
            chat_info_service: Сервис для получения информации о чатах.
            messaging_service: Сервис для отправки сообщений (опционально).
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._admin_command = admin_command_service
        self._chat_info_service = chat_info_service
        self._messaging = messaging_service

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

    async def send_welcome_message(
        self,
        chat_id: int,
        welcome_text: str,
    ) -> None:
        """Отправляет приветственное сообщение в чат.

        Инкапсулирует всю логику отправки и обработки ошибок.

        Args:
            chat_id: ID чата для отправки сообщения.
            welcome_text: Текст приветственного сообщения.

        Side Effects:
            - Отправляет приветственное сообщение через messaging_service.
            - Логирует ошибки отправки.
        """
        if self._messaging is None:
            self.logger.warning("MessagingService не доступен, пропускаем отправку приветствия")
            return

        try:
            await self._messaging.send_message(chat_id=chat_id, text=welcome_text)
            self.logger.info(f"Приветственное сообщение отправлено в чат {chat_id}")
        except Exception as e:
            # Логируем ошибку, но не прерываем работу
            self.logger.error(
                f"Ошибка при отправке приветствия в чат {chat_id}: {e}",
                exc_info=True,
            )

    @staticmethod
    def determine_bot_status_change(
        old_status: str | None,
        new_status: str | None,
    ) -> BotStatusChange:
        """Определяет изменение статуса бота в чате.

        Анализирует переходы между статусами для определения, был ли бот добавлен
        или удален из чата.

        Args:
            old_status: Предыдущий статус бота в чате (может быть None для новых чатов).
            new_status: Новый статус бота в чате.

        Returns:
            BotStatusChange с информацией о том, был ли бот добавлен или удален.
        """
        # Статусы, когда бот активен в чате
        active_statuses = {"member", "administrator", "restricted"}
        # Статусы, когда бот не в чате
        inactive_statuses = {"left", "kicked", None}

        # Определяем, был ли бот добавлен
        was_added = new_status in active_statuses and old_status in inactive_statuses

        # Определяем, был ли бот удален
        was_removed = new_status in inactive_statuses and old_status in active_statuses

        return BotStatusChange(
            was_added=was_added,
            was_removed=was_removed,
            old_status=old_status,
            new_status=new_status,
        )

    def extract_chat_event_data(
        self,
        update: Update,
    ) -> tuple[int, BotStatusChange] | None:
        """Извлекает данные о событии чата из Update.

        Парсит update.my_chat_member и извлекает chat_id и изменение статуса.

        Args:
            update: Объект обновления Telegram.

        Returns:
            Кортеж (chat_id, BotStatusChange) если событие валидно, None иначе.
        """
        my_cm = update.my_chat_member
        if not my_cm:
            return None

        old = getattr(my_cm.old_chat_member, "status", None)
        new = getattr(my_cm.new_chat_member, "status", None)
        chat = my_cm.chat
        chat_id = chat.id

        status_change = self.determine_bot_status_change(old, new)

        return (chat_id, status_change)
