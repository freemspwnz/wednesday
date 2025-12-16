from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers import CommandHandlers
from services.bot_services import BotServices


class UserHandlers:
    """Обработчики пользовательских команд бота.

    Этот класс инкапсулирует только пользовательские команды (/start, /help, /frog)
    и обработчик неизвестных команд. Вся фактическая логика реализована в
    `CommandHandlers` и переиспользуется здесь через делегирование.

    Такой подход позволяет явно разделить ответственность по типам команд при
    регистрации хендлеров в `WednesdayBot`, не дублируя реализацию.
    """

    def __init__(
        self,
        services: BotServices,
        next_run_provider: Callable[[], datetime | None] | None = None,
    ) -> None:
        self._core = CommandHandlers(services=services, next_run_provider=next_run_provider)

    @property
    def core(self) -> CommandHandlers:
        """Возвращает базовый объект `CommandHandlers` для переиспользования в других наборах хендлеров."""

        return self._core

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Делегирует обработку команды /start в основной `CommandHandlers`."""

        await self._core.start_command(update, context)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Делегирует обработку команды /help в основной `CommandHandlers`."""

        await self._core.help_command(update, context)

    async def frog_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Делегирует обработку команды /frog в основной `CommandHandlers`."""

        await self._core.frog_command(update, context)

    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Делегирует обработку неизвестных команд в основной `CommandHandlers`."""

        await self._core.unknown_command(update, context)
