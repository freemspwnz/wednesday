"""Регистратор обработчиков команд для SupportBot."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.ext import Application, ChatMemberHandler, CommandHandler, MessageHandler, filters

from bot.chat_event_handler import ChatEventHandler
from shared.protocols import ILogger

if TYPE_CHECKING:
    from bot.bot_error_handler import BotErrorHandler
    from bot.handlers_support import SupportBotHandlers


class SupportBotHandlersRegistry:
    """Регистратор обработчиков команд для SupportBot.

    Инкапсулирует логику регистрации всех обработчиков команд и событий
    в PTB Application для SupportBot. Отвечает только за конфигурацию обработчиков.

    Соблюдает принцип единственной ответственности (SRP): отвечает только
    за регистрацию обработчиков, не содержит бизнес-логики.
    """

    def __init__(
        self,
        application: Application,
        support_handlers: SupportBotHandlers,
        chat_event_handler: ChatEventHandler,
        error_handler: BotErrorHandler,
        logger: ILogger,
    ) -> None:
        """Инициализирует регистратор обработчиков для SupportBot.

        Args:
            application: PTB Application для регистрации обработчиков.
            support_handlers: Экземпляр SupportBotHandlers с методами обработчиков команд.
            chat_event_handler: Обработчик событий чата.
            error_handler: Глобальный обработчик ошибок.
            logger: Экземпляр логгера.
        """
        self.application = application
        self.support_handlers = support_handlers
        self.chat_event_handler = chat_event_handler
        self.error_handler = error_handler
        self.logger = logger

    def register_all(self) -> None:
        """Регистрирует все обработчики команд и событий для SupportBot.

        Side Effects:
            - Регистрирует все обработчики команд через application.add_handler().
            - Регистрирует обработчик событий ChatMemberHandler.
            - Регистрирует глобальный обработчик ошибок.
        """
        self.logger.info("Начало настройки обработчиков команд для SupportBot")

        # Команды SupportBot
        self._register_support_handlers()

        # Обработчик неизвестных команд
        self._register_unknown_command_handler()

        # Обработчик событий чата
        self._register_chat_event_handler()

        # Глобальный обработчик ошибок
        self._register_error_handler()

        self.logger.info("Обработчики команд для SupportBot успешно настроены и зарегистрированы")

    def _register_support_handlers(self) -> None:
        """Регистрирует команды SupportBot."""
        self.application.add_handler(CommandHandler("start", self.support_handlers.start_main_command))
        self.application.add_handler(CommandHandler("help", self.support_handlers.help_command))
        self.application.add_handler(CommandHandler("log", self.support_handlers.log_command))

    def _register_unknown_command_handler(self) -> None:
        """Регистрирует обработчик неизвестных команд."""
        self.application.add_handler(
            MessageHandler(filters.COMMAND, self.support_handlers.maintenance_message),
        )

    def _register_chat_event_handler(self) -> None:
        """Регистрирует обработчик событий чата."""
        self.application.add_handler(
            ChatMemberHandler(
                self.chat_event_handler.on_my_chat_member,
                ChatMemberHandler.MY_CHAT_MEMBER,
            ),
        )

    def _register_error_handler(self) -> None:
        """Регистрирует глобальный обработчик ошибок."""
        if hasattr(self.application, "add_error_handler"):
            self.application.add_error_handler(self.error_handler.handle_error)
