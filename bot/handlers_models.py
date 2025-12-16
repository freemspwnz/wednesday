from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers import CommandHandlers
from services.bot_services import BotServices


class ModelHandlers:
    """Обработчики команд управления моделями (Kandinsky и GigaChat).

    Вынесены отдельно для явного разделения зон ответственности:
    - выбор и перечисление моделей генерации изображений;
    - выбор и перечисление моделей текстового клиента.
    Фактическая логика команд реализована в `CommandHandlers` и вызывается через делегирование.
    """

    def __init__(
        self,
        services: BotServices,
        next_run_provider: Callable[[], datetime | None] | None = None,
    ) -> None:
        # next_run_provider здесь не используется, но принимается для унификации сигнатуры
        # с другими наборами хендлеров и потенциального будущего расширения.
        self._core = CommandHandlers(services=services, next_run_provider=next_run_provider)

    @property
    def core(self) -> CommandHandlers:
        """Возвращает базовый объект `CommandHandlers`."""

        return self._core

    async def set_kandinsky_model_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.set_kandinsky_model_command(update, context)

    async def set_gigachat_model_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.set_gigachat_model_command(update, context)

    async def list_models_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._core.list_models_command(update, context)
