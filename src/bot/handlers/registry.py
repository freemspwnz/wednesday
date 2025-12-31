"""Регистратор обработчиков команд для PTB Application."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.ext import Application, ChatMemberHandler, CommandHandler, MessageHandler, filters

from bot.handlers.admin import AdminHandlers
from bot.handlers.chat_event import ChatEventHandler
from bot.handlers.models import ModelHandlers
from bot.handlers.user import UserHandlers
from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    from bot.bot_error_handler import BotErrorHandler


class BotHandlersRegistry:
    """Регистратор обработчиков команд для основного бота.

    Инкапсулирует логику регистрации всех обработчиков команд и событий
    в PTB Application. Отвечает только за конфигурацию обработчиков.

    Соблюдает принцип единственной ответственности (SRP): отвечает только
    за регистрацию обработчиков, не содержит бизнес-логики.
    """

    def __init__(  # noqa: PLR0913, PLR0917
        self,
        application: Application,
        user_handlers: UserHandlers,
        admin_handlers: AdminHandlers,
        model_handlers: ModelHandlers,
        chat_event_handler: ChatEventHandler,
        error_handler: BotErrorHandler,
        logger: ILogger,
    ) -> None:
        """Инициализирует регистратор обработчиков.

        Args:
            application: PTB Application для регистрации обработчиков.
            user_handlers: Обработчики пользовательских команд.
            admin_handlers: Обработчики административных команд.
            model_handlers: Обработчики команд управления моделями.
            chat_event_handler: Обработчик событий чата.
            error_handler: Глобальный обработчик ошибок.
            logger: Экземпляр логгера.
        """
        self.application = application
        self.user_handlers = user_handlers
        self.admin_handlers = admin_handlers
        self.model_handlers = model_handlers
        self.chat_event_handler = chat_event_handler
        self.error_handler = error_handler
        self.logger = logger

    def register_all(self) -> None:
        """Регистрирует все обработчики команд и событий.

        Side Effects:
            - Регистрирует все обработчики команд через application.add_handler().
            - Регистрирует обработчик событий ChatMemberHandler.
            - Регистрирует глобальный обработчик ошибок.
        """
        self.logger.info("Начало настройки обработчиков команд")

        # Пользовательские команды
        self._register_user_handlers()

        # Административные команды
        self._register_admin_handlers()

        # Команды управления моделями
        self._register_model_handlers()

        # Обработчик неизвестных команд
        self._register_unknown_command_handler()

        # Обработчик событий чата
        self._register_chat_event_handler()

        # Глобальный обработчик ошибок
        self._register_error_handler()

        self.logger.info("Обработчики команд успешно настроены и зарегистрированы")

    def _register_user_handlers(self) -> None:
        """Регистрирует пользовательские команды."""
        self.application.add_handler(CommandHandler("start", self.user_handlers.start_command))
        self.application.add_handler(CommandHandler("help", self.user_handlers.help_command))
        self.application.add_handler(CommandHandler("frog", self.user_handlers.frog_command))

    def _register_admin_handlers(self) -> None:
        """Регистрирует административные команды."""
        self.application.add_handler(CommandHandler("status", self.admin_handlers.status_command))
        self.application.add_handler(
            CommandHandler("force_send", self.admin_handlers.admin_force_send_command),
        )
        self.application.add_handler(CommandHandler("log", self.admin_handlers.admin_log_command))
        self.application.add_handler(
            CommandHandler("add_chat", self.admin_handlers.admin_add_chat_command),
        )
        self.application.add_handler(
            CommandHandler("remove_chat", self.admin_handlers.admin_remove_chat_command),
        )
        self.application.add_handler(CommandHandler("stop", self.admin_handlers.stop_command))
        self.application.add_handler(CommandHandler("list_chats", self.admin_handlers.list_chats_command))
        self.application.add_handler(CommandHandler("mod", self.admin_handlers.mod_command))
        self.application.add_handler(CommandHandler("unmod", self.admin_handlers.unmod_command))
        self.application.add_handler(CommandHandler("list_mods", self.admin_handlers.list_mods_command))
        self.application.add_handler(
            CommandHandler("set_frog_limit", self.admin_handlers.set_frog_limit_command),
        )
        self.application.add_handler(
            CommandHandler("set_frog_used", self.admin_handlers.set_frog_used_command),
        )

    def _register_model_handlers(self) -> None:
        """Регистрирует команды управления моделями."""
        self.application.add_handler(
            CommandHandler("set_kandinsky_model", self.model_handlers.set_kandinsky_model_command),
        )
        self.application.add_handler(
            CommandHandler("set_gigachat_model", self.model_handlers.set_gigachat_model_command),
        )
        self.application.add_handler(CommandHandler("list_models", self.model_handlers.list_models_command))

    def _register_unknown_command_handler(self) -> None:
        """Регистрирует обработчик неизвестных команд."""
        self.application.add_handler(MessageHandler(filters.COMMAND, self.user_handlers.unknown_command))

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
