"""Application service для координации обработки запросов генерации жабы по команде /frog.

Координирует работу:
- ImageService (генерация изображений)
- FrogDeliveryService (доставка изображений, включая fallback)
- IUsageTracker (обновление usage)
- AdminNotificationService (уведомление администраторов)
"""

from __future__ import annotations

import traceback
from typing import Any

from app.admin_notification_service import AdminNotificationService
from app.frog_delivery_service import FrogDeliveryService
from app.image_service import ImageService
from shared.base.base_service import BaseService
from shared.base.exceptions import (
    CircuitBreakerOpen,
    ImageGenerationError,
    MessagingError,
    UnexpectedImageError,
)
from shared.protocols import ILogger, IUsageTracker


class FrogProcessingService(BaseService):
    """Application service для координации обработки запросов генерации жабы.

    Координирует работу:
    - ImageService (генерация изображений)
    - FrogDeliveryService (доставка изображений, включая fallback)
    - IUsageTracker (обновление usage)
    - AdminNotificationService (уведомление администраторов)
    """

    def __init__(
        self,
        image_service: ImageService,
        delivery_service: FrogDeliveryService,
        usage_tracker: IUsageTracker | None = None,
        admin_notifier: AdminNotificationService | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис координации.

        Args:
            image_service: Сервис генерации изображений.
            delivery_service: Сервис доставки изображений (основных и fallback).
            usage_tracker: Трекер использования (опционально).
            admin_notifier: Сервис уведомления администраторов (опционально).
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._image_service = image_service
        self._delivery_service = delivery_service
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
            image_data, caption = await self._image_service.generate_frog_image(user_id=user_id)

            # 2. Отправка изображения через delivery service
            success = await self._delivery_service.send_image_to_user(
                chat_id=chat_id,
                user_id=user_id,
                image_data=image_data,
                caption=caption,
                status_message_id=status_message_id,
            )

            if not success:
                # Ошибка отправки - MessagingError уже обработан в delivery service
                return {"status": "failed", "error": "Не удалось отправить изображение"}

            # 3. Обновление usage (не критично для успешной отправки)
            if self._usage_tracker:
                try:
                    await self._usage_tracker.increment(1)
                except (MemoryError, SystemExit, KeyboardInterrupt):
                    # Системные ошибки пробрасываем выше даже для не критичных операций
                    raise
                except BaseException as e:
                    # Ошибка обновления usage не критична, только логируем
                    self.logger.warning(
                        f"Ошибка обновления usage: {e}",
                        event="usage_update_failed",
                        status="warning",
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )

            return {"status": "success"}

        except CircuitBreakerOpen as e:
            # Явная обработка открытого circuit breaker
            # Координатор решает стратегию - используем fallback
            self.logger.warning(
                f"Circuit breaker открыт, используем fallback: {e}",
                event="circuit_breaker_open",
                status="circuit_breaker",
                user_id=user_id,
                chat_id=chat_id,
            )
            return await self._handle_generation_failure(
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message_id,
                error_details=f"Circuit breaker открыт: {e}",
            )
        except ImageGenerationError as e:
            # Ожидаемая ошибка генерации - используем fallback
            return await self._handle_generation_failure(
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message_id,
                error_details=f"Ошибка генерации изображения: {e}",
            )
        except UnexpectedImageError as e:
            # Неожиданная ошибка генерации
            return await self._handle_unexpected_error(
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message_id,
                error=e,
            )
        except MessagingError:
            # Ошибка отправки уже обработана в delivery service
            # Пробрасываем для верхнего уровня
            raise
        except (MemoryError, SystemExit, KeyboardInterrupt):
            # Системные ошибки пробрасываем выше без обёртки
            raise
        except BaseException as e:
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

        # Используем delivery service для fallback
        await self._delivery_service.send_fallback_to_user(
            chat_id=chat_id,
            user_id=user_id,
            image_service=self._image_service,
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
        error: BaseException,
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

        # Используем delivery service для fallback
        await self._delivery_service.send_fallback_to_user(
            chat_id=chat_id,
            user_id=user_id,
            image_service=self._image_service,
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
