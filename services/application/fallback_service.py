"""Сервис для обработки fallback сценариев при ошибках генерации."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from services.application.dispatch_execution_service import DispatchExecutionService
from services.application.dispatch_service import DispatchResult
from services.application.image_service import ImageService
from services.base.base_service import BaseService
from services.protocols import IMetrics
from utils.dispatch_registry import DispatchRegistry


class FallbackService(BaseService):
    """Сервис для обработки fallback сценариев.

    Отвечает за:
    - Обработку ошибок генерации изображения
    - Отправку fallback изображений (случайное сохранённое)
    - Обработку неожиданных ошибок
    - Логирование и метрики ошибок
    """

    def __init__(
        self,
        image_service: ImageService | None,
        dispatch_execution_service: DispatchExecutionService,
        dispatch_registry: DispatchRegistry,
        metrics: IMetrics | None = None,
    ) -> None:
        """Инициализирует сервис fallback.

        Args:
            image_service: Сервис генерации изображений для получения fallback.
            dispatch_execution_service: Сервис выполнения отправки.
            dispatch_registry: Реестр отправок для проверки.
            metrics: Сервис метрик.
        """
        super().__init__()
        self._image_service = image_service
        self._dispatch_execution_service = dispatch_execution_service
        self._dispatch_registry = dispatch_registry
        self._metrics = metrics

    async def send_fallback_to_targets(  # noqa: PLR0913, PLR0917
        self,
        slot_date: str,
        slot_time: str,
        targets: set[int],
        send_user_friendly_error: Callable[[int], Awaitable[None]],
        send_fallback_image: Callable[[int], Awaitable[bool]],
        result: DispatchResult,
    ) -> None:
        """Отправляет fallback изображение во все целевые чаты.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            targets: Множество ID целевых чатов.
            send_user_friendly_error: Коллбек для отправки дружелюбного сообщения об ошибке в чат.
            send_fallback_image: Коллбек для отправки fallback‑изображения в чат.
            result: Результат рассылки для обновления.
        """
        for target_chat in targets:
            try:
                # Проверяем, не было ли уже отправлено в этот чат в этот тайм-слот
                if await self._dispatch_registry.is_dispatched(
                    slot_date,
                    slot_time,
                    target_chat,
                ):
                    self.logger.info(
                        f"Пропускаем fallback отправку в {target_chat} - уже отправлено в слот {slot_date}_{slot_time}",
                    )
                    continue

                # Отправляем дружелюбное сообщение
                await send_user_friendly_error(target_chat)

                # Отправляем случайное изображение
                if await send_fallback_image(target_chat):
                    # Отмечаем в реестре успешную отправку
                    await self._dispatch_registry.mark_dispatched(
                        slot_date,
                        slot_time,
                        target_chat,
                    )
                    if self._metrics:
                        try:
                            await self._metrics.increment_dispatch_success()
                        except Exception:  # pragma: no cover
                            pass
                    result["success_count"] += 1

            except Exception as send_error:
                self.logger.error(f"Ошибка при отправке fallback в чат {target_chat}: {send_error}")
                result["failed_count"] += 1

    async def handle_generation_failure(  # noqa: PLR0913, PLR0917
        self,
        slot_date: str,
        slot_time: str,
        targets: set[int],
        send_admin_error: Callable[[str], Awaitable[None]],
        send_user_friendly_error: Callable[[int], Awaitable[None]],
        send_fallback_image: Callable[[int], Awaitable[bool]],
        result: DispatchResult,
    ) -> DispatchResult:
        """Обрабатывает ошибку генерации изображения.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            targets: Множество ID целевых чатов.
            send_admin_error: Коллбек для отправки детального сообщения об ошибке администраторам.
            send_user_friendly_error: Коллбек для отправки дружелюбного сообщения об ошибке в чат.
            send_fallback_image: Коллбек для отправки fallback‑изображения в чат.
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
        await send_admin_error(error_details)

        result["used_fallback"] = True

        # Пытаемся отправить fallback
        await self.send_fallback_to_targets(
            slot_date=slot_date,
            slot_time=slot_time,
            targets=targets,
            send_user_friendly_error=send_user_friendly_error,
            send_fallback_image=send_fallback_image,
            result=result,
        )

        return result

    async def handle_unexpected_error(  # noqa: PLR0913, PLR0917
        self,
        error: Exception,
        slot_date: str,
        slot_time: str,
        targets: set[int],
        send_admin_error: Callable[[str], Awaitable[None]],
        send_user_friendly_error: Callable[[int], Awaitable[None]],
        send_fallback_image: Callable[[int], Awaitable[bool]],
        result: DispatchResult,
    ) -> DispatchResult:
        """Обрабатывает неожиданную ошибку.

        Args:
            error: Исключение, которое произошло.
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            targets: Множество ID целевых чатов.
            send_admin_error: Коллбек для отправки детального сообщения об ошибке администраторам.
            send_user_friendly_error: Коллбек для отправки дружелюбного сообщения об ошибке в чат.
            send_fallback_image: Коллбек для отправки fallback‑изображения в чат.
            result: Результат рассылки для обновления.

        Returns:
            DispatchResult с обновленными счетчиками.
        """
        import traceback

        error_details = f"Произошла ошибка при отправке жабы: {error!s}"
        self.logger.error(error_details, exc_info=True)

        # Отправляем детальное сообщение администратору с трейcом
        full_error = traceback.format_exc()
        # Обрезаем трейс до последних 2000 символов (важная информация обычно в конце)
        max_trace_length = 2000
        if len(full_error) > max_trace_length:
            full_error = "..." + full_error[-max_trace_length:]
        await send_admin_error(
            f"{error_details}\n\nТрейс (последние {max_trace_length} символов):\n{full_error}",
        )

        result["used_fallback"] = True

        # Пытаемся отправить fallback
        await self.send_fallback_to_targets(
            slot_date=slot_date,
            slot_time=slot_time,
            targets=targets,
            send_user_friendly_error=send_user_friendly_error,
            send_fallback_image=send_fallback_image,
            result=result,
        )

        if self._metrics:
            try:
                await self._metrics.increment_dispatch_failed()
            except Exception:  # pragma: no cover
                pass

        return result
