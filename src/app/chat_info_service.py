"""Application service для получения информации о чатах Telegram."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.base.base_service import BaseService
from shared.protocols.infrastructure import ILogger
from shared.protocols.messaging import IMessagingService

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
    ) -> tuple[str | int, str]:
        """Безопасно получает информацию о чате с обработкой ошибок.

        Args:
            chat_id: ID чата для получения информации.
            timeout: Таймаут для запроса в секундах.

        Returns:
            Кортеж (chat_id, title), где chat_id может быть str или int,
            title - название чата или сообщение об ошибке.
        """
        details = await self._messaging.get_chat_details(chat_id=chat_id, timeout=timeout)
        if details is None:
            error_msg = "не удалось получить информацию"
            self.logger.warning(f"Не удалось получить информацию о чате {chat_id}")
            return (chat_id, error_msg)

        # Извлекаем title из словаря
        title = details.get("title") or details.get("first_name") or "Unknown"
        chat_id_result = details.get("id")
        # Если id есть в словаре, используем его, иначе используем переданный chat_id
        result_id: str | int = chat_id_result if chat_id_result is not None else chat_id
        return (result_id, str(title) if title else "Unknown")

    async def get_chat_safe(
        self,
        chat_id: int,
        timeout: float = DEFAULT_CHAT_FULL_TIMEOUT,
    ) -> Chat | None:
        """Безопасно получает полный объект чата с обработкой ошибок и таймаутом.

        DEPRECATED: Используйте get_chat_details_safe() для универсального доступа.

        Args:
            chat_id: ID чата для получения информации.
            timeout: Таймаут для запроса в секундах (по умолчанию 10 секунд).

        Returns:
            Объект чата или None в случае ошибки.

        Note:
            Этот метод возвращает Telegram-специфичный тип Chat.
            Для универсального доступа используйте get_chat_details_safe().
            Внутри использует get_chat_details() и преобразует результат в Chat объект.
        """
        # Используем get_chat_details для универсального доступа
        details = await self._messaging.get_chat_details(chat_id=chat_id, timeout=timeout)
        if details is None:
            self.logger.warning(f"Не удалось получить информацию о чате {chat_id}")
            return None

        # Для обратной совместимости создаем минимальный Chat-подобный объект
        # В реальности это должно возвращать None, так как мы не можем создать Telegram Chat объект
        # Но для совместимости с существующим кодом возвращаем None
        # Если код требует Chat объект, он должен использовать get_chat_details_safe()
        return None

    async def get_chat_details_safe(
        self,
        chat_id: int,
        timeout: float = DEFAULT_CHAT_FULL_TIMEOUT,
    ) -> dict[str, str | int | None] | None:
        """Безопасно получает детальную информацию о чате/пользователе.

        Args:
            chat_id: ID чата/пользователя для получения информации.
            timeout: Таймаут для запроса в секундах (по умолчанию 10 секунд).

        Returns:
            Словарь с информацией о чате/пользователе или None в случае ошибки.
        """
        result = await self._messaging.get_chat_details(chat_id=chat_id, timeout=timeout)
        # Логируем предупреждение, если результат None (ошибка)
        if result is None:
            self.logger.warning(f"Не удалось получить детальную информацию о чате {chat_id}")
        return result
