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

    @map_telegram_exceptions
    async def delete_message(
        self,
        chat_id: int,
        message_id: int,
    ) -> None:
        """Удаляет сообщение из чата.

        Args:
            chat_id: ID чата.
            message_id: ID сообщения для удаления.

        Raises:
            MessagingNetworkError: При сетевых ошибках.
            MessagingAPIError: При ошибках API (сообщение не найдено, нет прав).
        """
        await self._bot.delete_message(
            chat_id=chat_id,
            message_id=message_id,
        )

    @map_telegram_exceptions
    async def send_error_message(
        self,
        main_chat_id: int,
        message: str,
    ) -> None:
        """Отправляет сообщение об ошибке в основной чат.

        Args:
            main_chat_id: ID основного чата для отправки.
            message: Текст сообщения об ошибке.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        error_message = f"⚠️ {message}\nПопробуем в следующий раз! 🐸"
        await self._bot.send_message(
            chat_id=main_chat_id,
            text=error_message,
        )

    @map_telegram_exceptions
    async def send_user_friendly_error(
        self,
        chat_id: int,
    ) -> None:
        """Отправляет дружелюбное сообщение об ошибке в указанный чат.

        Args:
            chat_id: ID чата для отправки сообщения.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        friendly_message = (
            "🐸 К сожалению, не удалось сгенерировать новую картинку.\n"
            "Но не расстраивайтесь! Вот случайная картинка из архива! 🎲"
        )
        await self._bot.send_message(
            chat_id=chat_id,
            text=friendly_message,
        )

    @map_telegram_exceptions
    async def send_fallback_image(
        self,
        chat_id: int,
        image_data: bytes,
        caption: str,
    ) -> bool:
        """Отправляет fallback изображение в указанный чат.

        Args:
            chat_id: ID чата для отправки изображения.
            image_data: Байты изображения.
            caption: Подпись к изображению.

        Returns:
            True если изображение успешно отправлено, False если произошла ошибка.

        Raises:
            MessagingNetworkError: При сетевых ошибках (таймаут, ошибка соединения).
            MessagingAPIError: При ошибках API (токен, права, chat_not_found).
        """
        await self._bot.send_photo(
            chat_id=chat_id,
            photo=image_data,
            caption=caption,
        )
        return True
