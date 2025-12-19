"""
Базовый класс для обработчиков команд бота.

Содержит общие утилитарные методы, используемые всеми специализированными
наборами хендлеров (UserHandlers, AdminHandlers, ModelHandlers).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TypeVar

from telegram import Bot, Message, Update
from telegram.ext import ContextTypes

from services.bot_services import BotServices
from utils.admins_repo import AdminsRepo
from utils.logger import get_logger
from utils.retry import (
    retry_on_connect_error as global_retry_on_connect_error,
    retry_telegram,
)

# Константы
MAX_RETRIES_DEFAULT = 3  # количество попыток по умолчанию
RETRY_DELAY_DEFAULT = 2.0  # задержка между попытками по умолчанию

T = TypeVar("T")


class BaseHandlers:
    """Базовый класс для обработчиков команд с общими утилитарными методами."""

    def __init__(self, services: BotServices) -> None:
        """Инициализирует базовый класс обработчиков.

        Args:
            services: Контейнер сервисов бота для доступа к зависимостям.
        """
        self.logger = get_logger(__name__)
        self.services: BotServices = services
        self.admins_store: AdminsRepo = AdminsRepo()

    async def _send_log_file(self, bot: Bot, chat_id: int, path: Path) -> None:
        """Асинхронно читает лог‑файл с диска и отправляет его как документ.

        Чтение файла выполняется в отдельном потоке через run_in_executor,
        чтобы избежать блокировки event loop при работе с файловой системой.
        """
        import asyncio

        loop = asyncio.get_running_loop()

        def _read_bytes(p: Path) -> bytes:
            return p.read_bytes()

        data = await loop.run_in_executor(None, _read_bytes, path)
        await self._retry_on_connect_error(
            bot.send_document,
            chat_id=chat_id,
            document=data,
            filename=path.name,
            max_retries=3,
            delay=2,
        )

    async def _extract_target_user_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
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
                self.logger.debug(f"_extract_target_user_id: найден через reply: {target_id}")
                return target_id

        # Приоритет 2: аргумент команды
        if context.args:
            if len(context.args) != 1:
                self.logger.debug(
                    f"_extract_target_user_id: неверное количество аргументов: {len(context.args)}",
                )
                return None

            try:
                target_id = int(context.args[0])
                self.logger.debug(f"_extract_target_user_id: найден через аргумент: {target_id}")
                return target_id
            except ValueError as e:
                self.logger.warning(f"_extract_target_user_id: не удалось преобразовать аргумент в int: {e}")
                return None

        return None

    def _is_super_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь главным администратором.

        Сравнивает user_id с settings.admin_chat_id (из .env через DI).

        Args:
            user_id: Идентификатор пользователя для проверки.

        Returns:
            True если user_id совпадает с admin_chat_id, False иначе.
        """
        admin_chat_id = self.services.settings.admin_chat_id
        if not admin_chat_id:
            return False

        return admin_chat_id == user_id

    @retry_telegram(max_retries=MAX_RETRIES_DEFAULT, delay=RETRY_DELAY_DEFAULT)
    async def _safe_reply_text(self, message: Message, text: str) -> None:  # noqa: PLR6301
        """Безопасная отправка текста с retry для Telegram/сетевых ошибок.

        Используется как сокращённая запись для типичного паттерна
        `_retry_on_connect_error(message.reply_text, ...)` в местах, где
        не требуется гибкая настройка retry-параметров.
        """
        await message.reply_text(text)

    async def _retry_on_connect_error(  # noqa: PLR6301
        self,
        func: Callable[..., Awaitable[T]],
        *args: object,
        max_retries: int = MAX_RETRIES_DEFAULT,
        delay: float = RETRY_DELAY_DEFAULT,
        **kwargs: object,
    ) -> T:
        """
        Выполняет функцию с повторными попытками при сетевых/Telgram-ошибках.

        Это тонкая обёртка вокруг общего helper'а `utils.retry.retry_on_connect_error`,
        оставленная для совместимости с существующими тестами, которые патчат
        `_retry_on_connect_error` через monkeypatch.

        Note:
            Метод остаётся instance method (а не staticmethod) намеренно, чтобы
            тесты могли патчить его через monkeypatch.setattr(handler, "_retry_on_connect_error", ...).
        """
        return await global_retry_on_connect_error(
            func,
            *args,
            max_retries=max_retries,
            delay=delay,
            handle_rate_limit=True,
            **kwargs,
        )
