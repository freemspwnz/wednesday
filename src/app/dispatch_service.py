"""Application‑сервис для cron‑логики отправки Wednesday Frog.

Координирует работу:
- TargetPreparationService (подготовка целей)
- DispatchDeliveryService (отправка изображений, включая fallback)
- ImageService (генерация изображений)
- AdminNotificationService (уведомление администраторов)
"""

from __future__ import annotations

import traceback

from app.admin_notification_service import AdminNotificationService
from app.dispatch_delivery_service import DispatchDeliveryService
from app.dispatch_targets_helper import DispatchResult
from app.image_service import ImageService
from app.target_preparation_service import TargetPreparationService
from shared.base.base_service import BaseService
from shared.base.exceptions import CircuitBreakerOpen, ImageGenerationError, ServiceError, UnexpectedDispatchError
from shared.protocols import ILogger, IMetrics


class DispatchService(BaseService):
    """Application‑сервис для выполнения рассылки Wednesday Frog.

    Координирует работу:
    - TargetPreparationService (подготовка целей)
    - DispatchDeliveryService (отправка изображений, включая fallback)
    - ImageService (генерация изображений)
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        target_preparation_service: TargetPreparationService,
        dispatch_delivery_service: DispatchDeliveryService,
        image_service: ImageService | None,
        admin_notifier: AdminNotificationService | None = None,
        metrics: IMetrics | None = None,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис рассылки.

        Args:
            target_preparation_service: Сервис подготовки целей.
            dispatch_delivery_service: Сервис доставки изображений (основных и fallback).
            image_service: Сервис генерации изображений (опционально).
            admin_notifier: Сервис уведомления администраторов (опционально).
            metrics: Сервис метрик (опционально).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._target_preparation_service = target_preparation_service
        self._dispatch_delivery_service = dispatch_delivery_service
        self._image_service = image_service
        self._admin_notifier = admin_notifier
        self._metrics = metrics

    @staticmethod
    def _init_result(slot_date: str, slot_time: str) -> DispatchResult:
        """Инициализирует результат рассылки.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.

        Returns:
            Инициализированный DispatchResult.
        """
        return DispatchResult(
            slot_date=slot_date,
            slot_time=slot_time,
            total_targets=0,
            success_count=0,
            failed_count=0,
            used_fallback=False,
        )

    async def send_wednesday_frog(
        self,
        *,
        slot_date: str,
        slot_time: str,
        main_chat_id: str | None,
    ) -> DispatchResult:
        """Выполняет рассылку жабы в указанный слот.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            main_chat_id: Основной чат (строковый ID) для рассылки, если задан.

        Returns:
            DispatchResult с агрегированными счетчиками по рассылке.
        """
        result = DispatchService._init_result(slot_date, slot_time)
        main_chat_id_int = int(str(main_chat_id)) if main_chat_id else None

        try:
            # 1. Подготовка целей
            targets = await self._target_preparation_service.prepare_targets(
                main_chat_id=main_chat_id,
            )
            result["total_targets"] = len(targets)

            if not targets:
                return result

            # 2. Проверка, не отправляли ли уже
            if await self._target_preparation_service.is_already_dispatched_for_all(
                slot_date=slot_date,
                slot_time=slot_time,
                targets=targets,
            ):
                self.logger.info(
                    f"Уже отправлено ранее для всех чатов в слот {slot_date}_{slot_time}. Пропускаю генерацию.",
                )
                return result

            # 3. Генерация изображения
            if not self._image_service:
                # Если сервис генерации не настроен, используем fallback
                return await self._handle_generation_failure(
                    slot_date=slot_date,
                    slot_time=slot_time,
                    targets=targets,
                    result=result,
                )

            try:
                image_data, caption = await self._image_service.generate_frog_image()
            except CircuitBreakerOpen as e:
                # Явная обработка открытого circuit breaker
                # Координатор решает стратегию - используем fallback
                self.logger.warning(
                    f"Circuit breaker открыт при рассылке, используем fallback: {e}",
                    event="dispatch_circuit_breaker_open",
                    status="circuit_breaker",
                )
                return await self._handle_generation_failure(
                    slot_date=slot_date,
                    slot_time=slot_time,
                    targets=targets,
                    result=result,
                )
            except ImageGenerationError as e:
                # Ожидаемая ошибка генерации - используем fallback
                self.logger.warning(
                    f"Ошибка генерации при рассылке, используем fallback: {e}",
                    event="dispatch_generation_error",
                    status="error",
                )
                return await self._handle_generation_failure(
                    slot_date=slot_date,
                    slot_time=slot_time,
                    targets=targets,
                    result=result,
                )

            # 4. Отправка успешно сгенерированного изображения
            return await self._dispatch_delivery_service.send_image_to_targets(
                targets=targets,
                slot_date=slot_date,
                slot_time=slot_time,
                image_data=image_data,
                caption=caption,
                main_chat_id=main_chat_id_int,
                result=result,
            )

        except ServiceError as e:
            # Ожидаемые ошибки сервисов (доменные/инфраструктурные) обрабатываем через fallback
            if "targets" not in locals():
                targets = await self._target_preparation_service.prepare_targets(
                    main_chat_id=main_chat_id,
                )
                result["total_targets"] = len(targets)

            return await self._handle_dispatch_unexpected_error(
                error=e,
                slot_date=slot_date,
                slot_time=slot_time,
                targets=targets,
                result=result,
            )
        except BaseException as e:
            # Получаем targets для fallback, если они еще не получены
            # Системные ошибки обрабатываются внутри handle_unexpected_error
            if "targets" not in locals():
                targets = await self._target_preparation_service.prepare_targets(
                    main_chat_id=main_chat_id,
                )
                result["total_targets"] = len(targets)

            # Логируем действительно неожиданную ошибку
            unexpected_error = self.handle_unexpected_error(
                e,
                UnexpectedDispatchError,
                message=f"Unexpected error during dispatch execution: {e}",
                context={"event": "unexpected_dispatch_error"},
            )

            return await self._handle_dispatch_unexpected_error(
                error=unexpected_error,
                slot_date=slot_date,
                slot_time=slot_time,
                targets=targets,
                result=result,
            )

    async def _handle_generation_failure(
        self,
        slot_date: str,
        slot_time: str,
        targets: set[int],
        result: DispatchResult,
    ) -> DispatchResult:
        """Обрабатывает ошибку генерации изображения.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            targets: Множество ID целевых чатов.
            result: Результат рассылки для обновления.

        Returns:
            DispatchResult с обновленными счетчиками.
        """
        error_details = (
            "Не удалось сгенерировать изображение жабы для среды. "
            "API вернул None (возможные причины: лимит API, circuit breaker, "
            "ошибка генерации)"
        )
        self.logger.error(error_details)

        # Отправляем детальное сообщение администратору
        if self._admin_notifier:
            await self._admin_notifier.notify_dispatch_failure(
                slot_date=slot_date,
                slot_time=slot_time,
                error_details=error_details,
            )

        result["used_fallback"] = True

        # Пытаемся отправить fallback
        await self._dispatch_delivery_service.send_fallback_to_targets(
            slot_date=slot_date,
            slot_time=slot_time,
            targets=targets,
            result=result,
        )

        return result

    async def _handle_dispatch_unexpected_error(
        self,
        error: BaseException,
        slot_date: str,
        slot_time: str,
        targets: set[int],
        result: DispatchResult,
    ) -> DispatchResult:
        """Обрабатывает неожиданную ошибку.

        Args:
            error: Исключение, которое произошло.
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            targets: Множество ID целевых чатов.
            result: Результат рассылки для обновления.

        Returns:
            DispatchResult с обновленными счетчиками.
        """
        error_details = f"Произошла ошибка при отправке жабы: {error!s}"
        self.logger.error(error_details, exc_info=True)

        # Отправляем детальное сообщение администратору с трейсом
        full_error = traceback.format_exc()
        # Обрезаем трейс до последних 2000 символов (важная информация обычно в конце)
        max_trace_length = 2000
        if len(full_error) > max_trace_length:
            full_error = "..." + full_error[-max_trace_length:]
        if self._admin_notifier:
            await self._admin_notifier.notify_dispatch_failure(
                slot_date=slot_date,
                slot_time=slot_time,
                error_details=f"{error_details}\n\nТрейс (последние {max_trace_length} символов):\n{full_error}",
                traceback_str=full_error,
            )

        result["used_fallback"] = True

        # Пытаемся отправить fallback
        await self._dispatch_delivery_service.send_fallback_to_targets(
            slot_date=slot_date,
            slot_time=slot_time,
            targets=targets,
            result=result,
        )

        if self._metrics:
            try:
                await self._metrics.increment_dispatch_failed_with_pool()
            except ServiceError:  # pragma: no cover
                pass

        return result
