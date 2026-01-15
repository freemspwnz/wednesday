"""Application service для извлечения данных пользователя из команд Telegram.

Инкапсулирует логику парсинга и извлечения user_id из reply-сообщений
и аргументов команд, соблюдая границы слоёв.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.base.base_service import BaseService
from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


class UserExtractionService(BaseService):
    """Сервис для извлечения данных пользователя из команд Telegram.

    Инкапсулирует логику парсинга и извлечения user_id из reply-сообщений
    и аргументов команд, соблюдая границы слоёв.
    """

    def __init__(
        self,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис извлечения данных пользователя.

        Args:
            logger: Экземпляр логгера.
        """
        super().__init__(logger)

    def extract_target_user_id(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int | None:
        """Извлекает target_user_id из reply или аргументов команды.

        Проверяет приоритеты:
        1. reply_to_message.from_user.id (если есть reply)
        2. context.args[0] (если ровно один аргумент и это число)

        Args:
            update: Объект обновления Telegram.
            context: Контекст бота с аргументами команды.

        Returns:
            user_id как int, если успешно определён, иначе None.
        """
        # Приоритет 1: reply на сообщение
        if update.message and update.message.reply_to_message:
            reply_user = update.message.reply_to_message.from_user
            if reply_user:
                target_id = int(reply_user.id)
                self.logger.debug(f"extract_target_user_id: найден через reply: {target_id}")
                return target_id

        # Приоритет 2: аргумент команды
        if context.args:
            if len(context.args) != 1:
                self.logger.debug(
                    f"extract_target_user_id: неверное количество аргументов: {len(context.args)}",
                )
                return None

            try:
                target_id = int(context.args[0])
                self.logger.debug(f"extract_target_user_id: найден через аргумент: {target_id}")
                return target_id
            except ValueError as e:
                self.logger.warning(f"extract_target_user_id: не удалось преобразовать аргумент в int: {e}")
                return None

        return None
