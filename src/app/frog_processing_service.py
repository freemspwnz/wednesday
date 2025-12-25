"""Application service для координации обработки запросов генерации жабы по команде /frog.

Координирует работу:
- ImageService (генерация изображений)
- FrogDeliveryService (доставка изображений, включая fallback)
- IUsageTracker (обновление usage)
- AdminNotificationService (уведомление администраторов)
"""

from __future__ import annotations

from typing import Literal, TypedDict

from app.admin_notification_service import AdminNotificationService
from app.frog_delivery_service import FrogDeliveryService
from app.image_service import ImageService
from shared.base.base_service import BaseService
from shared.base.exceptions import (
    CircuitBreakerOpen,
    ImageGenerationError,
    MessagingError,
    MessagingNetworkError,
    NetworkError,
    UnexpectedImageError,
)
from shared.protocols import ILogger, IUsageTracker


class FrogRequestResult(TypedDict):
    """Типизированный результат обработки запроса генерации жабы.

    Attributes:
        status: Статус обработки запроса ("success" или "failed").
        error: Описание ошибки, если status="failed", иначе None.
    """

    status: Literal["success", "failed"]
    error: str | None


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
    ) -> FrogRequestResult:
        """Обрабатывает запрос на генерацию и отправку жабы.

        Args:
            chat_id: ID чата для отправки.
            user_id: ID пользователя.
            status_message_id: ID статусного сообщения для удаления (опционально).

        Returns:
            FrogRequestResult с ключами:
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
                return FrogRequestResult(status="failed", error="Не удалось отправить изображение")

            # 3. Обновление usage (не критично для успешной отправки)
            if self._usage_tracker:
                try:
                    await self._usage_tracker.increment_with_pool(1)
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

            return FrogRequestResult(status="success", error=None)

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
        except (NetworkError, MessagingNetworkError) as e:
            # Connection errors - ожидаемые ошибки сети, обрабатываем с graceful degradation
            return await self._handle_connection_error(
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message_id,
                error=e,
            )
        except (ConnectionError, TimeoutError, OSError) as e:
            # Стандартные Python connection/timeout errors - тоже обрабатываем gracefully
            return await self._handle_connection_error(
                chat_id=chat_id,
                user_id=user_id,
                status_message_id=status_message_id,
                error=e,
            )
        except MessagingError:
            # Ошибка отправки уже обработана в delivery service
            # Пробрасываем для верхнего уровня
            raise
        except BaseException as e:
            # Действительно неожиданные ошибки - пробрасываем после логирования
            unexpected_error = self.handle_unexpected_error(
                e,
                UnexpectedImageError,
                message=f"Неожиданная ошибка при обработке команды /frog: {e}",
                context={
                    "event": "frog_request_unexpected_error",
                    "user_id": user_id,
                    "chat_id": chat_id,
                },
            )
            raise unexpected_error from e

    async def _handle_generation_failure(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None,
        error_details: str,
    ) -> FrogRequestResult:
        """Обрабатывает ситуацию, когда генерация не удалась.

        Args:
            chat_id: ID чата.
            user_id: ID пользователя.
            status_message_id: ID статусного сообщения.
            error_details: Детали ошибки.

        Returns:
            FrogRequestResult с status="failed" и описанием ошибки.
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

        return FrogRequestResult(status="failed", error=error_details)

    async def _handle_connection_error(
        self,
        chat_id: int,
        user_id: int,
        status_message_id: int | None,
        error: BaseException,
    ) -> FrogRequestResult:
        """Обрабатывает connection errors с graceful degradation (fallback).

        Args:
            chat_id: ID чата.
            user_id: ID пользователя.
            status_message_id: ID статусного сообщения.
            error: Исключение connection/network error.

        Returns:
            FrogRequestResult с status="failed" и описанием ошибки.
        """
        error_type = type(error).__name__
        error_str = str(error)

        # Логируем connection error как warning (ожидаемая ошибка)
        self.logger.warning(
            f"Connection error while processing /frog command: {error}",
            event="frog_connection_error",
            status="warning",
            user_id=user_id,
            chat_id=chat_id,
            error_type=error_type,
            error_message=error_str[:200],
        )

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

        # Используем delivery service для fallback (graceful degradation)
        await self._delivery_service.send_fallback_to_user(
            chat_id=chat_id,
            user_id=user_id,
            image_service=self._image_service,
            status_message_id=status_message_id,
            friendly_message=(
                "🐸 К сожалению, произошла ошибка подключения при генерации.\n"
                "Но не расстраивайтесь! Вот случайная картинка из архива! 🎲"
            ),
        )

        # Уведомление администраторов (без трейса для connection errors - это ожидаемые ошибки)
        if self._admin_notifier:
            await self._admin_notifier.notify_generation_failure(
                user_id=user_id,
                error_details=error_details,
            )

        return FrogRequestResult(status="failed", error=error_details)
