"""Application service для валидации аргументов команд Telegram.

Инкапсулирует логику проверки наличия и количества аргументов команд,
соблюдая границы слоёв.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.base.base_service import BaseService
from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    from telegram.ext import ContextTypes


class CommandValidationService(BaseService):
    """Сервис для валидации аргументов команд Telegram.

    Инкапсулирует логику проверки наличия и количества аргументов команд.
    """

    def __init__(
        self,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис валидации команд.

        Args:
            logger: Экземпляр логгера.
        """
        super().__init__(logger)

    @staticmethod
    def has_args(
        context: ContextTypes.DEFAULT_TYPE,
        min_count: int = 1,
    ) -> bool:
        """Проверяет наличие аргументов команды.

        Args:
            context: Контекст бота с аргументами команды.
            min_count: Минимальное количество аргументов (по умолчанию 1).

        Returns:
            True если аргументы присутствуют и их количество >= min_count, False иначе.
        """
        return context.args is not None and len(context.args) >= min_count
