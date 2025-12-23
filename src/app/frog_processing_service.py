"""Application service для обработки запросов генерации жабы по команде /frog."""

from __future__ import annotations

import traceback
from typing import Any

from app.admin_notification_service import AdminNotificationService
from app.image_service import ImageService
from shared.base.base_service import BaseService
from shared.base.exceptions import (
    MessagingError,
    UnexpectedImageError,
)
from shared.protocols import ILogger, IMessagingService, IUsageTracker


class FrogProcessingService(BaseService):
    """Application service для обработки запросов генерации жабы.

    Инкапсулирует всю бизнес-логику обработки команды /frog:
    - Генерация изображения
    - Отправка пользователю
    - Обновление usage
    - Удаление статусного сообщения
    - Fallback логика при ошибках
    - Уведомление администраторов
    """

    def __init__(
        self,
        image_service: ImageService,
        messaging_service: IMessagingService,
        usage_tracker: IUsageTracker | None = None,
        admin_notifier: AdminNotificationService | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис обработки запросов.

        Args:
            image_service: Сервис генерации изображений.
            messaging_service: Сервис отправки сообщений.
            usage_tracker: Трекер использования (опционально).
            admin_notifier: Сервис уведомления администраторов (опционально).
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._image_service = image_service
        self._messaging = messaging_service
        self._usage_tracker = usage_tracker
        self._admin_notifier = admin_notifier

    async def process_frog_request(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None = None,
    ) -> dict[str, Any]:
        """Обрабатывает запрос на генерацию и отправку жабы.

        Args:
            chat_id: ID чата для отправки.
            user_id: ID пользователя.
            status_message_id: ID статусного сообщения для удаления (опционально).

        Returns:
            dict с ключами:
            - status: "success" | "failed"
            - error: описание ошибки (если status="failed")
        """
        try:
            # 1. Генерация изображения
            result = await self._image_service.generate_frog_image(user_id=user_id)

            if result:
                image_data, caption = result

                # 2. Отправка изображения
                await self._messaging.send_image(
                    chat_id=chat_id,
                    image=image_data,
                    caption=caption,
                )

                # 3. Обновление usage (не критично для успешной отправки)
                if self._usage_tracker:
                    try:
                        await self._usage_tracker.increment(1)
                    except Exception as e:
                        self.logger.warning(
                            f"Ошибка обновления usage: {e}",
                            event="usage_update_failed",
                            status="warning",
                            error_type=type(e).__name__,
                            error_message=str(e),
                        )

                # 4. Удаление статусного сообщения (не критично)
                if status_message_id:
                    try:
                        await self._messaging.delete_message(
                            chat_id=chat_id,
                            message_id=status_message_id,
                        )
                    except MessagingError as e:
                        self.logger.warning(
                            f"Не удалось удалить статусное сообщение: {e}",
                            event="status_message_delete_failed",
                            status="warning",
                            error_type=type(e).__name__,
                            error_message=str(e),
                        )

                self.logger.info(
                    f"Изображение жабы успешно отправлено пользователю {user_id} в чат {chat_id}",
                    event="frog_request_success",
                    status="ok",
                    user_id=user_id,
                    chat_id=chat_id,
                )

                return {"status": "success"}
            else:
                # Генерация не удалась - fallback
                return await self._handle_generation_failure(
                    chat_id=chat_id,
                    user_id=user_id,
                    status_message_id=status_message_id,
                    error_details="Не удалось сгенерировать изображение",
                )

        except UnexpectedImageError as e:
            # Неожиданная ошибка генерации
            return await self._handle_unexpected_error(
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message_id,
                error=e,
            )
        except MessagingError as e:
            # Ошибка отправки сообщения
            self.logger.error(
                f"Ошибка отправки изображения пользователю {user_id}: {e}",
                event="frog_request_messaging_error",
                status="error",
                user_id=user_id,
                chat_id=chat_id,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            # Удаляем статусное сообщение даже при ошибке отправки
            if status_message_id:
                try:
                    await self._messaging.delete_message(
                        chat_id=chat_id,
                        message_id=status_message_id,
                    )
                except Exception:
                    pass
            raise
        except Exception as e:
            # Любая другая неожиданная ошибка
            return await self._handle_unexpected_error(
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message_id,
                error=e,
            )

    async def _handle_generation_failure(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None,
        error_details: str,
    ) -> dict[str, Any]:
        """Обрабатывает ситуацию, когда генерация не удалась.

        Args:
            chat_id: ID чата.
            user_id: ID пользователя.
            status_message_id: ID статусного сообщения.
            error_details: Детали ошибки.

        Returns:
            dict с status="failed" и описанием ошибки.
        """
        self.logger.error(
            error_details,
            event="frog_generation_failed",
            status="error",
            user_id=user_id,
            chat_id=chat_id,
        )

        # Используем общую логику fallback
        await self._send_fallback_response(
            chat_id=chat_id,
            user_id=user_id,
            status_message_id=status_message_id,
            friendly_message=(
                "🐸 К сожалению, не удалось сгенерировать новую картинку.\n"
                "Но не расстраивайтесь! Вот случайная картинка из архива! 🎲"
            ),
        )

        # Уведомление администраторов
        if self._admin_notifier:
            await self._admin_notifier.notify_generation_failure(
                user_id=user_id,
                error_details=error_details,
            )

        return {"status": "failed", "error": error_details}

    async def _handle_unexpected_error(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None,
        error: Exception,
    ) -> dict[str, Any]:
        """Обрабатывает неожиданную ошибку.

        Args:
            chat_id: ID чата.
            user_id: ID пользователя.
            status_message_id: ID статусного сообщения.
            error: Исключение.

        Returns:
            dict с status="failed" и описанием ошибки.
        """
        error_type = type(error).__name__
        error_str = str(error)

        # Определяем тип ошибки для более информативного сообщения
        if "ConnectError" in error_type or "ConnectionError" in error_type or "Connection" in error_str:
            error_details = (
                f"Ошибка подключения к API при обработке команды /frog для пользователя {user_id}.\n"
                f"Тип: {error_type}\n"
                f"Детали: {error_str[:200]}\n\n"
                "Возможные причины:\n"
                "- Проблемы с интернет-соединением\n"
                "- Kandinsky API временно недоступен\n"
                "- Проблемы с прокси (если используется)\n"
                "- Блокировка доступа на стороне провайдера"
            )
        else:
            error_details = (
                f"Произошла ошибка при обработке команды /frog для пользователя {user_id}.\n"
                f"Тип: {error_type}\n"
                f"Детали: {error_str[:200]}"
            )

        self.logger.error(
            f"Ошибка при обработке /frog: {error_type} - {error_str}",
            event="frog_request_unexpected_error",
            status="error",
            user_id=user_id,
            chat_id=chat_id,
            error_type=error_type,
            error_message=error_str,
            exc_info=True,
        )

        # Используем общую логику fallback
        await self._send_fallback_response(
            chat_id=chat_id,
            user_id=user_id,
            status_message_id=status_message_id,
            friendly_message=(
                "🐸 К сожалению, произошла ошибка при генерации.\n"
                "Но не расстраивайтесь! Вот случайная картинка из архива! 🎲"
            ),
        )

        # Уведомление администраторов с трейсом
        if self._admin_notifier:
            full_trace = traceback.format_exc()
            await self._admin_notifier.notify_generation_failure(
                user_id=user_id,
                error_details=error_details,
                traceback_str=full_trace,
            )

        return {"status": "failed", "error": error_details}

    async def _send_fallback_response(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None,
        friendly_message: str,
    ) -> None:
        """Отправляет fallback-ответ при ошибке генерации.

        Выполняет:
        - Удаление статусного сообщения (если указано)
        - Отправку дружелюбного сообщения
        - Отправку случайного изображения из архива (если доступно)

        Args:
            chat_id: ID чата.
            user_id: ID пользователя.
            status_message_id: ID статусного сообщения для удаления (опционально).
            friendly_message: Текст дружелюбного сообщения.
        """
        # Удаление статусного сообщения
        if status_message_id:
            try:
                await self._messaging.delete_message(
                    chat_id=chat_id,
                    message_id=status_message_id,
                )
            except Exception:
                pass

        # Отправка дружелюбного сообщения
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
            )

        # Отправка случайного изображения
        fallback_image = await self._image_service.get_random_saved_image()
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
                )
            except MessagingError as e:
                self.logger.error(
                    f"Не удалось отправить fallback изображение: {e}",
                    event="fallback_image_send_failed",
                    status="error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
        else:
            self.logger.warning(
                "Нет сохраненных изображений для отправки как fallback",
                event="fallback_image_unavailable",
                status="warning",
                user_id=user_id,
            )
