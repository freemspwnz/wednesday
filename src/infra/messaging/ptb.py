"""Реализация IMessagingService через python-telegram-bot."""

from __future__ import annotations

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
        chat_id: int,
        image: bytes,
        caption: str,
    ) -> None:
        """Отправляет фото в указанный чат.

        Args:
            chat_id: ID чата для отправки.
            image: Байты изображения.
            caption: Подпись к изображению.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        await self._bot.send_photo(
            chat_id=chat_id,
            photo=image,
            caption=caption,
        )

    @map_telegram_exceptions
    async def send_message(
        self,
        chat_id: int,
        text: str,
    ) -> None:
        """Отправляет текстовое сообщение в указанный чат.

        Args:
            chat_id: ID чата для отправки.
            text: Текст сообщения.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        await self._bot.send_message(
            chat_id=chat_id,
            text=text,
        )
