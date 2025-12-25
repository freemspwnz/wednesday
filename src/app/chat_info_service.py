"""Application service для получения информации о чатах Telegram."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.base.base_service import BaseService
from shared.protocols import ILogger, IMessagingService

if TYPE_CHECKING:
    from telegram import Chat

# Константы для таймаутов
DEFAULT_CHAT_INFO_TIMEOUT = 5.0
DEFAULT_CHAT_FULL_TIMEOUT = 10.0


class ChatInfoService(BaseService):
    """Сервис для безопасного получения информации о чатах Telegram.

    Инкапсулирует логику получения информации о чатах через Telegram Bot API
    с обработкой ошибок и таймаутов. Предоставляет единый интерфейс для всех
    компонентов приложения, соблюдая архитектурные границы.
    """

    def __init__(
        self,
        messaging_service: IMessagingService,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис получения информации о чатах.

        Args:
            messaging_service: Сервис для работы с мессенджером (реализует IMessagingService).
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._messaging = messaging_service

    async def get_chat_info_safe(
        self,
        chat_id: int,
        timeout: float = DEFAULT_CHAT_INFO_TIMEOUT,
    ) -> tuple[int, str]:
        """Безопасно получает информацию о чате с обработкой ошибок.

        Args:
            chat_id: ID чата для получения информации.
            timeout: Таймаут для запроса в секундах.

        Returns:
            Кортеж (chat_id, title), где title - название чата или сообщение об ошибке.
        """
        result = await self._messaging.get_chat_info(chat_id=chat_id, timeout=timeout)
        # Логируем предупреждение, если получена ошибка
        if result[1].startswith("не удалось") or result[1].startswith("таймаут") or result[1].startswith("ошибка"):
            self.logger.warning(f"Не удалось получить информацию о чате {chat_id}: {result[1]}")
        return result

    async def get_chat_safe(
        self,
        chat_id: int,
        timeout: float = DEFAULT_CHAT_FULL_TIMEOUT,
    ) -> Chat | None:
        """Безопасно получает полный объект чата с обработкой ошибок и таймаутом.

        Args:
            chat_id: ID чата для получения информации.
            timeout: Таймаут для запроса в секундах (по умолчанию 10 секунд).

        Returns:
            Объект чата или None в случае ошибки.
        """
        result = await self._messaging.get_chat(chat_id=chat_id, timeout=timeout)
        # Логируем предупреждение, если результат None (ошибка)
        if result is None:
            self.logger.warning(f"Не удалось получить информацию о чате {chat_id}")
        return result
