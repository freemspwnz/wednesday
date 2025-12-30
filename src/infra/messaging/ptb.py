"""Реализация IMessagingService через python-telegram-bot."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from infra.messaging.ptb_exceptions import map_telegram_exceptions

if TYPE_CHECKING:
    from telegram import Bot


class PTBMessagingService:
    """Реализация IMessagingService через python-telegram-bot."""

    def __init__(self, bot: Bot) -> None:
        """Инициализирует сервис.

        Args:
            bot: Экземпляр Telegram Bot для отправки сообщений.
        """
        self._bot = bot

    @map_telegram_exceptions
    async def send_image(
        self,
        chat_id: str | int,
        image: bytes,
        caption: str,
    ) -> None:
        """Отправляет фото в указанный чат.

        Args:
            chat_id: ID чата для отправки (может быть str или int).
            image: Байты изображения.
            caption: Подпись к изображению.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        chat_id_int = int(chat_id) if isinstance(chat_id, str) else chat_id
        await self._bot.send_photo(
            chat_id=chat_id_int,
            photo=image,
            caption=caption,
        )

    @map_telegram_exceptions
    async def send_message(
        self,
        chat_id: str | int,
        text: str,
    ) -> None:
        """Отправляет текстовое сообщение в указанный чат.

        Args:
            chat_id: ID чата для отправки (может быть str или int).
            text: Текст сообщения.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        chat_id_int = int(chat_id) if isinstance(chat_id, str) else chat_id
        await self._bot.send_message(
            chat_id=chat_id_int,
            text=text,
        )

    @map_telegram_exceptions
    async def delete_message(
        self,
        chat_id: str | int,
        message_id: str | int,
    ) -> None:
        """Удаляет сообщение из чата.

        Args:
            chat_id: ID чата (может быть str или int).
            message_id: ID сообщения для удаления (может быть str или int).

        Raises:
            MessagingNetworkError: При сетевых ошибках.
            MessagingAPIError: При ошибках API (сообщение не найдено, нет прав).
        """
        chat_id_int = int(chat_id) if isinstance(chat_id, str) else chat_id
        message_id_int = int(message_id) if isinstance(message_id, str) else message_id
        await self._bot.delete_message(
            chat_id=chat_id_int,
            message_id=message_id_int,
        )

    async def get_chat_details(
        self,
        chat_id: str | int,
        timeout: float = 10.0,
    ) -> dict[str, str | int | None] | None:
        """Получает детальную информацию о чате/пользователе.

        Args:
            chat_id: ID чата/пользователя для получения информации (может быть str или int).
            timeout: Таймаут для запроса в секундах.

        Returns:
            Словарь с информацией о чате/пользователе или None в случае ошибки.
        """
        from telegram import Chat, User
        from telegram.error import NetworkError, TelegramError, TimedOut

        chat_id_int = int(chat_id) if isinstance(chat_id, str) else chat_id
        try:
            chat_info = await asyncio.wait_for(
                self._bot.get_chat(chat_id_int),
                timeout=timeout,
            )

            # Преобразуем Telegram объект в универсальный словарь
            if isinstance(chat_info, User):
                return {
                    "id": chat_info.id,
                    "title": None,
                    "first_name": chat_info.first_name,
                    "last_name": chat_info.last_name,
                    "username": chat_info.username,
                    "type": "user",
                }
            elif isinstance(chat_info, Chat):
                return {
                    "id": chat_info.id,
                    "title": getattr(chat_info, "title", None),
                    "first_name": getattr(chat_info, "first_name", None),
                    "last_name": getattr(chat_info, "last_name", None),
                    "username": getattr(chat_info, "username", None),
                    "type": chat_info.type,
                }
            else:
                # Fallback для неизвестных типов
                return {
                    "id": getattr(chat_info, "id", chat_id),
                    "title": getattr(chat_info, "title", None),
                    "first_name": getattr(chat_info, "first_name", None),
                    "last_name": getattr(chat_info, "last_name", None),
                    "username": getattr(chat_info, "username", None),
                    "type": "unknown",
                }
        except (TelegramError, NetworkError, TimedOut, TimeoutError, ValueError, TypeError, AttributeError):
            return None

    @map_telegram_exceptions
    async def send_file(
        self,
        chat_id: str | int,
        file: bytes,
        filename: str,
    ) -> None:
        """Отправляет файл в указанный чат.

        Args:
            chat_id: ID чата для отправки (может быть str или int).
            file: Байты файла.
            filename: Имя файла.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        chat_id_int = int(chat_id) if isinstance(chat_id, str) else chat_id
        await self._bot.send_document(
            chat_id=chat_id_int,
            document=file,
            filename=filename,
        )

    @map_telegram_exceptions
    async def send_reply(
        self,
        chat_id: str | int,
        text: str,
        reply_to_message_id: str | int | None = None,
    ) -> str | int:
        """Отправляет ответ на сообщение.

        Args:
            chat_id: ID чата для отправки (может быть str или int).
            text: Текст сообщения.
            reply_to_message_id: ID сообщения для ответа (опционально, может быть str или int).
                В Telegram используется message_id напрямую.

        Returns:
            ID отправленного сообщения (может быть str или int).

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        chat_id_int = int(chat_id) if isinstance(chat_id, str) else chat_id
        reply_id_int = int(reply_to_message_id) if isinstance(reply_to_message_id, str) else reply_to_message_id
        message = await self._bot.send_message(
            chat_id=chat_id_int,
            text=text,
            reply_to_message_id=reply_id_int,
        )
        # Telegram API всегда возвращает int для message_id
        return message.message_id  # type: ignore[no-any-return]

    @map_telegram_exceptions
    async def edit_message(
        self,
        chat_id: str | int,
        message_id: str | int,
        text: str,
    ) -> None:
        """Редактирует существующее сообщение.

        Telegram поддерживает редактирование сообщений.

        Args:
            chat_id: ID чата (может быть str или int).
            message_id: ID сообщения для редактирования (может быть str или int).
            text: Новый текст сообщения.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (сообщение не найдено, нет прав).
        """
        chat_id_int = int(chat_id) if isinstance(chat_id, str) else chat_id
        message_id_int = int(message_id) if isinstance(message_id, str) else message_id
        await self._bot.edit_message_text(
            chat_id=chat_id_int,
            message_id=message_id_int,
            text=text,
        )
