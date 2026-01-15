from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers.base import BaseHandlers
from bot.handlers.messages import (
    FROG_GENERATION_STATUS_MESSAGE,
    UNKNOWN_COMMAND_MESSAGE,
    WELCOME_MESSAGE_START,
)
from shared.bot_services import BotServices
from shared.protocols.infrastructure import ILogger


class UserHandlers(BaseHandlers):
    """Обработчики пользовательских команд бота.

    Этот класс инкапсулирует только пользовательские команды (/start, /help, /frog)
    и обработчик неизвестных команд. Содержит полную реализацию всех методов.
    """

    def __init__(
        self,
        services: BotServices,
        logger: ILogger,
    ) -> None:
        super().__init__(services, logger)
        if self.services.admin_access_service is None:
            raise ValueError("admin_access_service must be provided in BotServices")
        if self.services.help_message_service is None:
            raise ValueError("help_message_service must be provided in BotServices")
        if self.services.frog_command_service is None:
            raise ValueError("frog_command_service must be provided in BotServices")
        self._admin_access = self.services.admin_access_service
        self._help_message_service = self.services.help_message_service
        self._frog_command_service = self.services.frog_command_service

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start.

        Приветствует пользователя и показывает основную информацию о боте,
        включая доступные команды.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Отправляет приветственное сообщение пользователю.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        self.logger.info(f"Получена команда /start от пользователя {user.id}")

        welcome_message = WELCOME_MESSAGE_START

        success = await self._safe_reply_with_fallback(
            message,
            welcome_message,
        )
        if success:
            self.logger.info("Отправлено приветственное сообщение")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help.

        Показывает справку по командам бота. Для администраторов отображается
        расширенная админская справка со всеми доступными командами, для обычных
        пользователей - пользовательская справка с базовыми командами.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Делегирует всю логику (проверку прав и выбор сообщения) в help_message_service.
            - Отправляет соответствующую справку (админскую или пользовательскую).
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        user_id = user.id
        self.logger.info(f"Получена команда /help от пользователя {user_id}")

        # Делегируем всю логику (проверку прав и выбор сообщения) в сервис
        help_message = await self._help_message_service.build_help_message(
            user_id=user_id,
            admin_access_service=self._admin_access,
        )

        await self._safe_reply_with_fallback(
            message,
            help_message,
        )

    async def frog_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /frog.

        Делегирует всю бизнес-логику в FrogCommandService.
        Отвечает только за взаимодействие с Telegram API.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Отправляет статусное сообщение пользователю (если нужно).
            - Отправляет сообщение об ошибке пользователю (если есть).
            - Удаляет статусное сообщение при ошибке (если нужно).
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        user_id = user.id
        chat_id = message.chat_id
        self.logger.info(f"Получена команда /frog от пользователя {user_id}")

        # Проверяем, разрешена ли команда
        check_result = await self._frog_command_service.check_frog_command_allowed(user_id)

        # Если проверка не прошла, отправляем ошибку
        if not check_result.success:
            error_message = check_result.error_message or ""
            await self._safe_reply_with_fallback(message, error_message)
            return

        # Отправляем статусное сообщение
        status_message = await self._safe_reply_text_and_get_message(
            message,
            check_result.status_message or FROG_GENERATION_STATUS_MESSAGE,
        )

        # Ставим задачу в очередь
        enqueue_result = await self._frog_command_service.enqueue_frog_generation(
            chat_id=chat_id,
            user_id=user_id,
            status_message_id=status_message.message_id if status_message else None,
        )

        # Если была ошибка при постановке задачи, обрабатываем её
        if not enqueue_result.success:
            await self._safe_delete_message(status_message)
            if enqueue_result.error_message:
                await self._safe_reply_with_fallback(
                    message,
                    enqueue_result.error_message,
                )

    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик неизвестных команд.

        Обрабатывает любые команды, которые не распознаны другими обработчиками.
        Отправляет пользователю сообщение с подсказкой о доступных командах.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Отправляет сообщение с информацией о доступных командах пользователю.
            - Использует retry_on_connect_error() для обработки сетевых ошибок.
        """
        validated = self._validate_update(update)
        if validated is None:
            return
        message, user = validated

        user_id = user.id
        self.logger.info(f"Получена неизвестная команда от пользователя {user_id}")

        success = await self._safe_reply_with_fallback(
            message,
            UNKNOWN_COMMAND_MESSAGE,
        )
        if success:
            self.logger.info("Отправлено сообщение о неизвестной команде")
