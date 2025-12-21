"""Application‑сервис для cron‑логики отправки Wednesday Frog.

Координирует работу:
- TargetPreparationService (подготовка целей)
- DispatchExecutionService (выполнение отправки)
- FallbackService (обработка fallback)
- ImageService (генерация изображений)

Отправка сообщений в Telegram и форматирование пользовательских текстов
остаются в `WednesdayBot` и передаются сюда через коллбеки.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.dispatch_execution_service import DispatchExecutionService
from app.dispatch_result import DispatchResult
from app.fallback_service import FallbackService
from app.image_service import ImageService
from app.target_preparation_service import TargetPreparationService
from shared.base.base_service import BaseService
from shared.base.exceptions import ServiceError
from shared.protocols import ILogger


class DispatchService(BaseService):
    """Application‑сервис для выполнения рассылки Wednesday Frog.

    Координирует работу:
    - TargetPreparationService (подготовка целей)
    - DispatchExecutionService (выполнение отправки)
    - FallbackService (обработка fallback)
    - ImageService (генерация изображений)
    """

    def __init__(
        self,
        *,
        target_preparation_service: TargetPreparationService,
        dispatch_execution_service: DispatchExecutionService,
        fallback_service: FallbackService,
        image_service: ImageService | None,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис рассылки.

        Args:
            target_preparation_service: Сервис подготовки целей.
            dispatch_execution_service: Сервис выполнения отправки.
            fallback_service: Сервис обработки fallback.
            image_service: Сервис генерации изображений (опционально).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._target_preparation_service = target_preparation_service
        self._dispatch_execution_service = dispatch_execution_service
        self._fallback_service = fallback_service
        self._image_service = image_service

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

    async def send_wednesday_frog(  # noqa: PLR0913
        self,
        *,
        slot_date: str,
        slot_time: str,
        main_chat_id: str | None,
        send_error_message: Callable[[str], Awaitable[None]],
        send_admin_error: Callable[[str], Awaitable[None]],
        send_user_friendly_error: Callable[[int], Awaitable[None]],
        send_fallback_image: Callable[[int], Awaitable[bool]],
        send_image: Callable[..., Awaitable[None]],
    ) -> DispatchResult:
        """Выполняет рассылку жабы в указанный слот.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            main_chat_id: Основной чат (строковый ID) для рассылки, если задан.
            send_error_message: Коллбек для отправки краткого сообщения об ошибке в основной чат.
            send_admin_error: Коллбек для отправки детального сообщения об ошибке администраторам.
            send_user_friendly_error: Коллбек для отправки дружелюбного сообщения об ошибке в чат.
            send_fallback_image: Коллбек для отправки fallback‑изображения в чат.
            send_image: Коллбек для отправки изображения в Telegram.

        Returns:
            DispatchResult с агрегированными счетчиками по рассылке.
        """
        result = DispatchService._init_result(slot_date, slot_time)

        try:
            # 1. Подготовка целей
            targets = await self._target_preparation_service.prepare_targets(
                main_chat_id=main_chat_id,
                send_error_message=send_error_message,
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
            image_result = None
            if self._image_service:
                image_result = await self._image_service.generate_frog_image()

            # 4. Отправка
            if image_result:
                image_data, caption = image_result
                return await self._dispatch_execution_service.send_to_targets(
                    targets=targets,
                    slot_date=slot_date,
                    slot_time=slot_time,
                    image_data=image_data,
                    caption=caption,
                    send_error_message=send_error_message,
                    send_image=send_image,
                    result=result,
                )
            else:
                # Fallback
                return await self._fallback_service.handle_generation_failure(
                    slot_date=slot_date,
                    slot_time=slot_time,
                    targets=targets,
                    send_admin_error=send_admin_error,
                    send_user_friendly_error=send_user_friendly_error,
                    send_fallback_image=send_fallback_image,
                    result=result,
                )

        except Exception as e:
            import traceback

            # Получаем targets для fallback, если они еще не получены
            if "targets" not in locals():
                targets = await self._target_preparation_service.prepare_targets(
                    main_chat_id=main_chat_id,
                    send_error_message=send_error_message,
                )
                result["total_targets"] = len(targets)

            # Логируем неожиданную ошибку
            if not isinstance(e, ServiceError):
                self.logger.error(
                    f"Неожиданная ошибка при выполнении рассылки: {e}",
                    event="unexpected_dispatch_error",
                    status="error",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    traceback=traceback.format_exc(),
                )

            return await self._fallback_service.handle_unexpected_error(
                error=e,
                slot_date=slot_date,
                slot_time=slot_time,
                targets=targets,
                send_admin_error=send_admin_error,
                send_user_friendly_error=send_user_friendly_error,
                send_fallback_image=send_fallback_image,
                result=result,
            )
