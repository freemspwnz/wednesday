from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers import CommandHandlers
from services.bot_services import BotServices


class AdminHandlers:
    """Обработчики административных команд бота.

    Инкапсулирует команды управления ботом, логами, чатами и администраторами.
    Реализация команд остаётся в `CommandHandlers` и вызывается через делегирование,
    что сохраняет совместимость существующих тестов и минимизирует размер diff.
    """

    def __init__(
        self,
        services: BotServices,
        next_run_provider: Callable[[], datetime | None] | None = None,
    ) -> None:
        # Используем тот же базовый класс, что и пользовательские хендлеры,
        # чтобы не дублировать логику и состояние (rate limit, admins_store и т.п.).
        self._core = CommandHandlers(services=services, next_run_provider=next_run_provider)

    @property
    def core(self) -> CommandHandlers:
        """Возвращает базовый объект `CommandHandlers` для доступа к общим методам."""

        return self._core

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.status_command(update, context)

    async def admin_log_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.admin_log_command(update, context)

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.stop_command(update, context)

    async def admin_force_send_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.admin_force_send_command(update, context)

    async def admin_add_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.admin_add_chat_command(update, context)

    async def admin_remove_chat_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.admin_remove_chat_command(update, context)

    async def list_chats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.list_chats_command(update, context)

    async def set_frog_limit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.set_frog_limit_command(update, context)

    async def set_frog_used_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.set_frog_used_command(update, context)

    async def mod_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.mod_command(update, context)

    async def unmod_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.unmod_command(update, context)

    async def list_mods_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.list_mods_command(update, context)
