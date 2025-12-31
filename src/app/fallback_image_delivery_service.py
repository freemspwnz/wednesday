"""Application service для доставки fallback изображений.

Инкапсулирует общую логику получения и отправки fallback изображений,
используемую как в пользовательских запросах, так и в рассылках.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from shared.base.base_service import BaseService
from shared.base.exceptions import MessagingError
from shared.protocols.infrastructure import ILogger
from shared.protocols.messaging import IFallbackImageProvider, IMessagingService


class FallbackImageDeliveryService(BaseService):
    """Сервис для доставки fallback изображений.

    Отвечает за:
    - Получение fallback изображения из провайдера
    - Отправку дружелюбного сообщения (опционально, через callback или прямое сообщение)
    - Отправку fallback изображения
    - Обработку ошибок получения/отправки

    НЕ отвечает за:
    - Удаление status-сообщений (специфика пользовательских запросов)
    - Регистрацию в dispatch registry (специфика рассылок)
    - Обновление метрик (специфика рассылок)
    - Работу с множеством чатов (координация на уровне выше)
    """

    def __init__(
        self,
        image_provider: IFallbackImageProvider,
        messaging_service: IMessagingService,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис доставки fallback изображений.

        Args:
            image_provider: Провайдер для получения fallback изображений.
            messaging_service: Сервис для отправки сообщений.
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._image_provider = image_provider
        self._messaging = messaging_service

    async def deliver_fallback_image(
        self,
        chat_id: int,
        friendly_message: str | None = None,
        send_friendly_message_func: Callable[[int], Awaitable[None]] | None = None,
        send_image_func: Callable[[int, bytes, str], Awaitable[bool]] | None = None,
    ) -> bool:
        """Доставляет fallback изображение в указанный чат.

        Атомарно отправляет дружелюбное сообщение (если указано) и fallback изображение.
        Если friendly_message_func передан, используется он, иначе friendly_message отправляется
        напрямую через messaging_service.

        Args:
            chat_id: ID чата для отправки.
            friendly_message: Текст дружелюбного сообщения (отправляется напрямую через messaging_service).
            send_friendly_message_func: Callback для отправки дружелюбного сообщения (если нужна кастомная логика).
            send_image_func: Кастомная функция отправки изображения.
                          Если None, используется стандартный send_image.

        Returns:
            True если изображение успешно отправлено, False иначе.
        """
        # 1. Отправка дружелюбного сообщения (если указано)
        if send_friendly_message_func is not None:
            # Используем кастомную функцию для отправки дружелюбного сообщения
            try:
                await send_friendly_message_func(chat_id)
            except MessagingError as e:
                self.logger.error(
                    f"Не удалось отправить дружелюбное сообщение через callback: {e}",
                    event="friendly_message_send_failed",
                    status="error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    chat_id=chat_id,
                )
                # Не критично, продолжаем отправку изображения
        elif friendly_message:
            # Отправляем напрямую через messaging_service
            await self._send_friendly_message(chat_id, friendly_message)

        # 2. Получение fallback изображения
        fallback_image = await self._image_provider.get_random_saved_image()
        if not fallback_image:
            self.logger.warning(
                "Нет сохраненных изображений для fallback",
                event="fallback_image_unavailable",
                status="warning",
                chat_id=chat_id,
            )
            return False

        image_data, caption = fallback_image

        # 3. Отправка изображения (используем кастомную функцию или стандартную)
        send_func = send_image_func or self._default_send_image
        try:
            success = await send_func(chat_id, image_data, caption)
            if success:
                self.logger.info(
                    "Fallback изображение успешно отправлено",
                    event="fallback_image_sent",
                    status="ok",
                    chat_id=chat_id,
                )
            return success
        except MessagingError as e:
            self.logger.error(
                f"Ошибка отправки fallback изображения: {e}",
                event="fallback_image_send_failed",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
                chat_id=chat_id,
            )
            return False

    async def _send_friendly_message(
        self,
        chat_id: int,
        message: str,
    ) -> None:
        """Отправляет дружелюбное сообщение напрямую через messaging_service."""
        try:
            await self._messaging.send_message(chat_id=chat_id, text=message)
        except MessagingError as e:
            self.logger.error(
                f"Не удалось отправить дружелюбное сообщение: {e}",
                event="friendly_message_send_failed",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
                chat_id=chat_id,
            )
            # Не критично, продолжаем отправку изображения

    async def _default_send_image(
        self,
        chat_id: int,
        image_data: bytes,
        caption: str,
    ) -> bool:
        """Стандартная функция отправки изображения через messaging_service."""
        await self._messaging.send_image(
            chat_id=chat_id,
            image=image_data,
            caption=caption,
        )
        return True
