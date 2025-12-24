"""Унифицированный сервис для доставки изображений пользователям.

Объединяет функциональность отправки основного изображения и fallback-изображений
для пользовательских запросов /frog в единый сервис.
"""

from __future__ import annotations

from app.image_service import ImageService
from shared.base.base_service import BaseService
from shared.base.exceptions import MessagingError
from shared.protocols import ILogger, IMessagingService
from shared.retry import retry_on_connect_error


class FrogDeliveryService(BaseService):
    """Унифицированный сервис для доставки изображений пользователям.

    Отвечает за:
    - Отправку основного изображения пользователю
    - Отправку fallback изображений пользователю
    - Удаление статусных сообщений
    - Обработку ошибок отправки
    """

    def __init__(
        self,
        messaging_service: IMessagingService,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис доставки.

        Args:
            messaging_service: Сервис отправки сообщений.
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._messaging = messaging_service

    async def send_image_to_user(
        self,
        chat_id: int,
        user_id: int,
        image_data: bytes,
        caption: str,
        status_message_id: int | None = None,
    ) -> bool:
        """Отправляет основное изображение пользователю.

        Args:
            chat_id: ID чата для отправки.
            user_id: ID пользователя (для логирования).
            image_data: Байты изображения.
            caption: Подпись к изображению.
            status_message_id: ID статусного сообщения для удаления (опционально).

        Returns:
            True если отправка успешна, False иначе.
        """
        try:
            # Отправка изображения с retry
            await retry_on_connect_error(
                self._messaging.send_image,
                chat_id=chat_id,
                image=image_data,
                caption=caption,
                max_retries=3,
                delay=2.0,
                handle_rate_limit=True,
            )

            # Удаление статусного сообщения (не критично)
            if status_message_id:
                await self._delete_status_message_safe(chat_id, status_message_id)

            self.logger.info(
                f"Изображение жабы успешно отправлено пользователю {user_id} в чат {chat_id}",
                event="frog_image_sent",
                status="ok",
                user_id=user_id,
                chat_id=chat_id,
            )
            return True

        except MessagingError as e:
            # Ошибка отправки сообщения
            self.logger.error(
                f"Ошибка отправки изображения пользователю {user_id}: {e}",
                event="frog_image_send_failed",
                status="error",
                user_id=user_id,
                chat_id=chat_id,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            # Удаляем статусное сообщение даже при ошибке отправки
            if status_message_id:
                await self._delete_status_message_safe(chat_id, status_message_id)
            return False

    async def send_fallback_to_user(
        self,
        chat_id: int,
        user_id: int,
        image_service: ImageService,
        status_message_id: int | None = None,
        friendly_message: str | None = None,
    ) -> None:
        """Отправляет fallback изображение пользователю.

        Args:
            chat_id: ID чата для отправки.
            user_id: ID пользователя (для логирования).
            image_service: Сервис генерации изображений для получения fallback.
            status_message_id: ID статусного сообщения для удаления (опционально).
            friendly_message: Текст дружелюбного сообщения (опционально).
        """
        # Удаление статусного сообщения
        if status_message_id:
            await self._delete_status_message_safe(chat_id, status_message_id)

        # Отправка дружелюбного сообщения
        if friendly_message:
            try:
                await self._messaging.send_message(
                    chat_id=chat_id,
                    text=friendly_message,
                )
            except MessagingError as e:
                self.logger.error(
                    f"Не удалось отправить дружелюбное сообщение: {e}",
                    event="friendly_message_send_failed",
                    status="error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    user_id=user_id,
                    chat_id=chat_id,
                )

        # Отправка случайного изображения
        fallback_image = await image_service.get_random_saved_image()
        if fallback_image:
            fallback_image_data, fallback_caption = fallback_image
            try:
                await self._messaging.send_image(
                    chat_id=chat_id,
                    image=fallback_image_data,
                    caption=fallback_caption,
                )
                self.logger.info(
                    f"Случайное изображение отправлено пользователю {user_id} как fallback",
                    event="fallback_image_sent",
                    status="ok",
                    user_id=user_id,
                    chat_id=chat_id,
                )
            except MessagingError as e:
                self.logger.error(
                    f"Не удалось отправить fallback изображение: {e}",
                    event="fallback_image_send_failed",
                    status="error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    user_id=user_id,
                    chat_id=chat_id,
                )
        else:
            self.logger.warning(
                "Нет сохраненных изображений для отправки как fallback",
                event="fallback_image_unavailable",
                status="warning",
                user_id=user_id,
                chat_id=chat_id,
            )

    async def _delete_status_message_safe(
        self,
        chat_id: int,
        message_id: int,
    ) -> None:
        """Безопасно удаляет статусное сообщение.

        Args:
            chat_id: ID чата.
            message_id: ID сообщения для удаления.
        """
        try:
            await self._messaging.delete_message(
                chat_id=chat_id,
                message_id=message_id,
            )
        except (MemoryError, SystemExit, KeyboardInterrupt):
            # Системные ошибки пробрасываем выше
            raise
        except BaseException:
            # Игнорируем другие ошибки при удалении статусного сообщения (не критично)
            pass
