"""Унифицированный сервис для отправки изображений (основных и fallback).

Объединяет функциональность отправки основного изображения и fallback-изображений
в единый сервис для устранения дублирования и упрощения архитектуры.
"""

from __future__ import annotations

from app.database_operations_service import DatabaseOperationsService
from app.dispatch_targets_helper import DispatchResult, process_targets_with_registry_check
from app.image_service import ImageService
from shared.base.base_service import BaseService
from shared.base.exceptions import (
    AppError,
    MessagingAPIError,
    MessagingNetworkError,
    RepoError,
    ServiceError,
    UnexpectedDispatchError,
)
from shared.protocols import IDispatchRegistry, ILogger, IMessagingService, IMetrics
from shared.retry import retry_on_connect_error


class DispatchDeliveryService(BaseService):
    """Унифицированный сервис для отправки изображений в целевые чаты.

    Отвечает за:
    - Отправку основного изображения во все целевые чаты
    - Отправку fallback изображений во все целевые чаты
    - Регистрацию отправок в dispatch registry
    - Обработку ошибок отправки
    - Запись метрик
    """

    def __init__(  # noqa: PLR0913
        self,
        dispatch_registry: IDispatchRegistry,
        database_operations: DatabaseOperationsService,
        messaging_service: IMessagingService,
        image_service: ImageService | None = None,
        metrics: IMetrics | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис доставки.

        Args:
            dispatch_registry: Реестр отправок для регистрации.
            database_operations: Сервис для групповых операций БД в транзакциях.
            messaging_service: Сервис отправки сообщений.
            image_service: Сервис генерации изображений для получения fallback (опционально).
            metrics: Сервис метрик (опционально).
            logger: Экземпляр логгера для использования в сервисе.
        """
        super().__init__(logger)
        self._dispatch_registry = dispatch_registry
        self._database_operations = database_operations
        self._messaging = messaging_service
        self._image_service = image_service
        self._metrics = metrics

    async def send_image_to_targets(  # noqa: PLR0913, PLR0917
        self,
        targets: set[int],
        slot_date: str,
        slot_time: str,
        image_data: bytes,
        caption: str,
        main_chat_id: int | None = None,
        result: DispatchResult | None = None,
    ) -> DispatchResult:
        """Отправляет основное изображение во все целевые чаты.

        Args:
            targets: Множество ID целевых чатов.
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            image_data: Байты изображения.
            caption: Подпись к изображению.
            main_chat_id: ID основного чата для отправки сообщений об ошибках (опционально).
            result: Результат рассылки для обновления счетчиков.

        Returns:
            DispatchResult с обновленными счетчиками.
        """
        if result is None:
            result = DispatchResult(
                slot_date=slot_date,
                slot_time=slot_time,
                total_targets=len(targets),
                success_count=0,
                failed_count=0,
                used_fallback=False,
            )

        async def _send_for_single_target(
            target_chat: int,
            current_result: DispatchResult,
        ) -> None:
            await self._send_single_image(
                target_chat=target_chat,
                slot_date=slot_date,
                slot_time=slot_time,
                image_data=image_data,
                caption=caption,
                main_chat_id=main_chat_id,
                result=current_result,
            )

        await process_targets_with_registry_check(
            dispatch_registry=self._dispatch_registry,
            logger=self.logger,
            slot_date=slot_date,
            slot_time=slot_time,
            targets=targets,
            result=result,
            per_target_sender=_send_for_single_target,
            skip_log_event="dispatch_already_sent",
        )

        return result

    async def send_fallback_to_targets(
        self,
        slot_date: str,
        slot_time: str,
        targets: set[int],
        result: DispatchResult | None = None,
    ) -> DispatchResult:
        """Отправляет fallback изображение во все целевые чаты.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            targets: Множество ID целевых чатов.
            result: Результат рассылки для обновления.

        Returns:
            DispatchResult с обновленными счетчиками.
        """
        if result is None:
            result = DispatchResult(
                slot_date=slot_date,
                slot_time=slot_time,
                total_targets=len(targets),
                success_count=0,
                failed_count=0,
                used_fallback=True,
            )

        if self._image_service is None:
            self.logger.warning("ImageService недоступен для отправки fallback изображений")
            return result

        image_service = self._image_service  # Для type narrowing

        async def _send_fallback_for_single_target(
            target_chat: int,
            current_result: DispatchResult,
        ) -> None:
            try:
                # Отправляем дружелюбное сообщение
                await self._messaging.send_user_friendly_error(target_chat)

                # Получаем fallback изображение
                fallback_image = await image_service.get_random_saved_image()
                if fallback_image:
                    image_data, caption = fallback_image
                    # Отправляем случайное изображение
                    if await self._messaging.send_fallback_image(
                        chat_id=target_chat,
                        image_data=image_data,
                        caption=caption,
                    ):
                        # Используем DatabaseOperationsService для атомарной регистрации
                        try:
                            await self._database_operations.record_dispatch_success(
                                slot_date=slot_date,
                                slot_time=slot_time,
                                chat_id=target_chat,
                            )
                        except RepoError as e:
                            self.logger.warning(
                                f"Ошибка при регистрации fallback отправки: {e}",
                                event="fallback_registration_error",
                                status="warning",
                                error_type=type(e).__name__,
                                error_message=str(e),
                                chat_id=target_chat,
                                slot_date=slot_date,
                                slot_time=slot_time,
                            )
                            # Отправка успешна, но регистрация не удалась
                            # Это менее критично, чем сама отправка
                        current_result["success_count"] += 1
                else:
                    self.logger.warning(
                        f"Нет сохраненных изображений для fallback в чат {target_chat}",
                        event="fallback_image_unavailable",
                        status="warning",
                        chat_id=target_chat,
                    )

            except AppError as send_error:
                # Ожидаемые ошибки приложения при отправке fallback сообщений
                self.logger.error(
                    f"Ошибка приложения при отправке fallback в чат {target_chat}: {send_error}",
                    event="fallback_app_error",
                    status="error",
                    error_type=type(send_error).__name__,
                    error_message=str(send_error),
                    chat_id=target_chat,
                )
                current_result["failed_count"] += 1
            except BaseException as send_error:
                # Действительно неожиданные ошибки при отправке fallback
                # Системные ошибки обрабатываются внутри handle_unexpected_error
                unexpected_error = self.handle_unexpected_error(
                    send_error,
                    UnexpectedDispatchError,
                    message=f"Unexpected error while sending fallback to chat {target_chat}: {send_error}",
                    context={
                        "event": "fallback_send_error",
                        "chat_id": target_chat,
                    },
                )
                # Не продолжаем немедленно рассылку при неожиданных ошибках,
                # пусть верхний уровень решит стратегию обработки
                raise unexpected_error from send_error

        await process_targets_with_registry_check(
            dispatch_registry=self._dispatch_registry,
            logger=self.logger,
            slot_date=slot_date,
            slot_time=slot_time,
            targets=targets,
            result=result,
            per_target_sender=_send_fallback_for_single_target,
            skip_log_event="fallback_already_sent",
        )

        return result

    async def _send_single_image(  # noqa: PLR0913, PLR0917
        self,
        target_chat: int,
        slot_date: str,
        slot_time: str,
        image_data: bytes,
        caption: str,
        main_chat_id: int | None,
        result: DispatchResult,
    ) -> bool:
        """Отправляет одно изображение в целевой чат.

        Args:
            target_chat: ID целевого чата.
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            image_data: Байты изображения.
            caption: Подпись к изображению.
            main_chat_id: ID основного чата для отправки сообщений об ошибках (опционально).
            result: Результат рассылки для обновления счетчиков.

        Returns:
            True если отправка успешна, False иначе.
        """
        try:
            await retry_on_connect_error(
                self._messaging.send_image,
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
            except RepoError as e:
                self.logger.warning(
                    f"Ошибка при регистрации отправки: {e}",
                    event="dispatch_registration_error",
                    status="warning",
                    error_type=type(e).__name__,
                    error_message=str(e),
                    chat_id=target_chat,
                    slot_date=slot_date,
                    slot_time=slot_time,
                )
                # Отправка успешна, но регистрация не удалась
                # Это менее критично, чем сама отправка
            result["success_count"] += 1
            self.logger.info(f"Жаба отправлена в чат {target_chat}")
            return True

        except (MessagingNetworkError, MessagingAPIError) as send_error:
            return await self._handle_messaging_error(
                send_error=send_error,
                target_chat=target_chat,
                main_chat_id=main_chat_id,
                result=result,
            )
        except AppError as send_error:
            return await self._handle_app_error(
                send_error=send_error,
                target_chat=target_chat,
                main_chat_id=main_chat_id,
                result=result,
            )
        except BaseException as send_error:
            # Действительно неожиданные программные ошибки
            # Системные ошибки обрабатываются внутри handle_unexpected_error
            unexpected_error = self.handle_unexpected_error(
                send_error,
                UnexpectedDispatchError,
                message=f"Неожиданная ошибка при отправке изображения в чат {target_chat}: {send_error}",
                context={
                    "event": "unexpected_dispatch_error",
                    "chat_id": target_chat,
                },
            )
            raise unexpected_error from send_error

    async def _handle_messaging_error(
        self,
        send_error: MessagingNetworkError | MessagingAPIError,
        target_chat: int,
        main_chat_id: int | None,
        result: DispatchResult,
    ) -> bool:
        """Обрабатывает сетевые/Telegram ошибки отправки.

        Args:
            send_error: Ошибка отправки.
            target_chat: ID целевого чата.
            main_chat_id: ID основного чата для отправки сообщений об ошибках (опционально).
            result: Результат рассылки для обновления.

        Returns:
            False (отправка не удалась).
        """
        is_network = isinstance(send_error, MessagingNetworkError)
        log_msg = (
            f"Сетевая/Telegram-ошибка отправки в чат {target_chat}: {send_error}"
            if is_network
            else f"Ошибка Telegram API при отправке в чат {target_chat}: {send_error}"
        )
        self.logger.error(log_msg)

        await self._notify_error_and_update_metrics(
            main_chat_id=main_chat_id,
            error_message=f"Не удалось отправить изображение в чат {target_chat}",
            result=result,
        )
        return False

    async def _handle_app_error(
        self,
        send_error: AppError,
        target_chat: int,
        main_chat_id: int | None,
        result: DispatchResult,
    ) -> bool:
        """Обрабатывает ожидаемые ошибки приложения.

        Args:
            send_error: Ошибка приложения.
            target_chat: ID целевого чата.
            main_chat_id: ID основного чата для отправки сообщений об ошибках (опционально).
            result: Результат рассылки для обновления.

        Returns:
            False (отправка не удалась).
        """
        self.logger.error(
            f"Ошибка приложения при отправке изображения в чат {target_chat}: {send_error}",
            event="dispatch_app_error",
            status="error",
            error_type=type(send_error).__name__,
            error_message=str(send_error),
            chat_id=target_chat,
        )

        await self._notify_error_and_update_metrics(
            main_chat_id=main_chat_id,
            error_message=f"Не удалось отправить изображение в чат {target_chat} из-за ошибки приложения",
            result=result,
        )
        return False

    async def _notify_error_and_update_metrics(
        self,
        main_chat_id: int | None,
        error_message: str,
        result: DispatchResult,
    ) -> None:
        """Уведомляет об ошибке и обновляет метрики (best-effort).

        Args:
            main_chat_id: ID основного чата для отправки сообщений об ошибках (опционально).
            error_message: Текст сообщения об ошибке.
            result: Результат рассылки для обновления.
        """
        if main_chat_id is not None:
            try:
                await self._messaging.send_error_message(
                    main_chat_id=main_chat_id,
                    message=error_message,
                )
            except ServiceError:  # pragma: no cover - уведомление не критично
                pass
        try:
            if self._metrics:
                # Используем helper-метод для получения connection из pool (вне UoW контекста)
                if hasattr(self._metrics, 'increment_dispatch_failed_with_pool'):
                    await self._metrics.increment_dispatch_failed_with_pool()
                else:
                    # Fallback для совместимости
                    import asyncpg

                    if hasattr(self._metrics, '_pool'):
                        pool: asyncpg.Pool = self._metrics._pool  # type: ignore[attr-defined]
                        async with pool.acquire() as conn:
                            await self._metrics.increment_dispatch_failed(connection=conn)
        except ServiceError:  # pragma: no cover
            pass
        result["failed_count"] += 1
