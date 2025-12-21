"""Сервис для выполнения отправки сообщений."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from app.database_operations_service import DatabaseOperationsService
from app.dispatch_result import DispatchResult
from infra.repos.dispatch_registry import DispatchRegistry
from shared.base.base_service import BaseService
from shared.base.exceptions import MessagingAPIError, MessagingNetworkError
from shared.protocols import IMetrics, IUsageTracker
from shared.retry import retry_on_connect_error


class DispatchExecutionService(BaseService):
    """Сервис для выполнения отправки сообщений в целевые чаты.

    Отвечает за:
    - Отправку одного фото в чат
    - Отправку во все целевые чаты
    - Регистрацию отправок в dispatch registry
    - Запись метрик
    """

    def __init__(
        self,
        dispatch_registry: DispatchRegistry,
        metrics: IMetrics,
        usage_tracker: IUsageTracker,
        database_operations: DatabaseOperationsService | None = None,
    ) -> None:
        """Инициализирует сервис выполнения отправки.

        Args:
            dispatch_registry: Реестр отправок для регистрации.
            metrics: Сервис метрик.
            usage_tracker: Трекер использования.
            database_operations: Сервис для групповых операций БД в транзакциях (опционально).
        """
        super().__init__()
        self._dispatch_registry = dispatch_registry
        self._metrics = metrics
        self._usage_tracker = usage_tracker

        # Создаём DatabaseOperationsService, если не передан
        if database_operations is None:
            database_operations = DatabaseOperationsService(
                dispatch_registry=dispatch_registry,
                usage_tracker=usage_tracker,
                metrics=metrics,
            )
        self._database_operations = database_operations

    async def send_single_image(  # noqa: PLR0913, PLR0917
        self,
        target_chat: int,
        slot_date: str,
        slot_time: str,
        image_data: bytes,
        caption: str,
        send_error_message: Callable[[str], Awaitable[None]],
        send_image: Callable[..., Awaitable[None]],
        result: DispatchResult,
    ) -> bool:
        """Отправляет одно изображение в целевой чат.

        Args:
            target_chat: ID целевого чата.
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            image_data: Байты изображения.
            caption: Подпись к изображению.
            send_error_message: Коллбек для отправки сообщения об ошибке.
            send_image: Коллбек для отправки изображения в Telegram (принимает именованные параметры).
            result: Результат рассылки для обновления счетчиков.

        Returns:
            True если отправка успешна, False иначе.
        """
        try:
            await retry_on_connect_error(
                send_image,
                chat_id=target_chat,
                image=image_data,
                caption=caption,
                max_retries=3,
                delay=2.0,
                handle_rate_limit=True,
            )
            # Используем DatabaseOperationsService для атомарной регистрации
            try:
                await self._database_operations.record_dispatch_success(
                    slot_date=slot_date,
                    slot_time=slot_time,
                    chat_id=target_chat,
                )
            except Exception as e:
                self.logger.error(f"Ошибка при регистрации отправки: {e}")
                # Отправка успешна, но регистрация не удалась
                # Это менее критично, чем сама отправка
            result["success_count"] += 1
            self.logger.info(f"Жаба отправлена в чат {target_chat}")
            return True

        except (MessagingNetworkError, MessagingAPIError) as send_error:
            # Сетевые/Telegram-ошибки после всех попыток
            is_network = isinstance(send_error, MessagingNetworkError)
            log_msg = (
                f"Сетевая/Telegram-ошибка отправки в чат {target_chat}: {send_error}"
                if is_network
                else f"Ошибка Telegram API при отправке в чат {target_chat}: {send_error}"
            )
            self.logger.error(log_msg)
            try:
                await send_error_message(
                    f"Не удалось отправить изображение в чат {target_chat}",
                )
            except Exception:  # pragma: no cover - уведомление не критично
                pass
            try:
                await self._metrics.increment_dispatch_failed()
            except Exception:  # pragma: no cover
                pass
            result["failed_count"] += 1
            return False
        except Exception as send_error:
            # Неожиданные программные ошибки
            self.logger.error(
                f"Неожиданная программная ошибка при отправке изображения в чат {target_chat}: {send_error}",
                exc_info=True,
            )
            try:
                await send_error_message(
                    f"Не удалось отправить изображение в чат {target_chat} из-за внутренней ошибки",
                )
            except Exception:  # pragma: no cover
                pass
            try:
                await self._metrics.increment_dispatch_failed()
            except Exception:  # pragma: no cover
                pass
            result["failed_count"] += 1
            return False

    async def send_to_targets(  # noqa: PLR0913, PLR0917
        self,
        targets: set[int],
        slot_date: str,
        slot_time: str,
        image_data: bytes,
        caption: str,
        send_error_message: Callable[[str], Awaitable[None]],
        send_image: Callable[..., Awaitable[None]],
        result: DispatchResult,
    ) -> DispatchResult:
        """Отправляет изображение во все целевые чаты.

        Args:
            targets: Множество ID целевых чатов.
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            image_data: Байты изображения.
            caption: Подпись к изображению.
            send_error_message: Коллбек для отправки сообщения об ошибке.
            send_image: Коллбек для отправки изображения в Telegram.
            result: Результат рассылки для обновления счетчиков.

        Returns:
            DispatchResult с обновленными счетчиками.
        """
        for target_chat in targets:
            # Проверяем, не было ли уже отправлено в этот чат в этот тайм-слот
            if await self._dispatch_registry.is_dispatched(
                slot_date,
                slot_time,
                target_chat,
            ):
                self.logger.info(
                    f"Пропускаем отправку в {target_chat} - уже отправлено в слот {slot_date}_{slot_time}",
                )
                continue

            await self.send_single_image(
                target_chat=target_chat,
                slot_date=slot_date,
                slot_time=slot_time,
                image_data=image_data,
                caption=caption,
                send_error_message=send_error_message,
                send_image=send_image,
                result=result,
            )

        return result
