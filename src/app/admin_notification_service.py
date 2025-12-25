"""Application service для уведомления администраторов об ошибках."""

from __future__ import annotations

from app.admin_notification_builders import (
    DispatchErrorData,
    DispatchErrorNotificationBuilder,
    GenerationErrorData,
    GenerationErrorNotificationBuilder,
)
from shared.base.base_service import BaseService
from shared.base.exceptions import MessagingError, RepoError, UnexpectedAppError
from shared.protocols import IAdminsRepo, ILogger, IMessagingService


class AdminNotificationService(BaseService):
    """Сервис для уведомления администраторов об ошибках и событиях.

    Отвечает только за координацию отправки уведомлений.
    Форматирование сообщений делегировано билдерам.
    """

    def __init__(
        self,
        messaging_service: IMessagingService,
        admins_repo: IAdminsRepo,
        generation_builder: GenerationErrorNotificationBuilder | None = None,
        dispatch_builder: DispatchErrorNotificationBuilder | None = None,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис уведомлений.

        Args:
            messaging_service: Сервис для отправки сообщений.
            admins_repo: Репозиторий администраторов.
            generation_builder: Билдер для сообщений об ошибках генерации.
            dispatch_builder: Билдер для сообщений об ошибках рассылки.
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._messaging = messaging_service
        self._admins_repo = admins_repo
        self._generation_builder = generation_builder or GenerationErrorNotificationBuilder()
        self._dispatch_builder = dispatch_builder or DispatchErrorNotificationBuilder()

    async def notify_generation_failure(
        self,
        user_id: int,
        error_details: str,
        traceback_str: str | None = None,
    ) -> None:
        """Уведомляет администраторов об ошибке генерации изображения.

        Args:
            user_id: ID пользователя, для которого произошла ошибка.
            error_details: Детали ошибки.
            traceback_str: Трейсбек ошибки (опционально).
        """
        try:
            all_admins = await self._admins_repo.list_all_admins()
            if not all_admins:
                self.logger.warning(
                    "Нет администраторов для уведомления",
                    event="admin_notification_skipped",
                    status="warning",
                )
                return

            # Используем билдер для форматирования
            data = GenerationErrorData(
                user_id=user_id,
                error_details=error_details,
                traceback_str=traceback_str,
            )

            # Проверяем длину и выбираем формат
            if self._generation_builder.should_use_short(data):
                admin_message = self._generation_builder.build_short(data)
            else:
                admin_message = self._generation_builder.build(data)

            # Отправляем каждому админу
            for admin_id in all_admins:
                try:
                    await self._messaging.send_message(
                        chat_id=admin_id,
                        text=admin_message,
                    )

                    self.logger.info(
                        f"Уведомление отправлено администратору {admin_id}",
                        event="admin_notification_sent",
                        status="ok",
                        admin_id=admin_id,
                    )
                except MessagingError as e:
                    # Ошибка отправки конкретному админу - логируем, но продолжаем
                    self.logger.error(
                        f"Не удалось отправить уведомление админу {admin_id}: {e}",
                        event="admin_notification_failed",
                        status="error",
                        admin_id=admin_id,
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
        except RepoError as e:
            # Ошибка получения списка админов - критично, но не падаем
            self.logger.error(
                f"Ошибка при получении списка администраторов: {e}",
                event="admin_repo_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
        except BaseException as e:
            # Неожиданная ошибка - логируем через handle_unexpected_error
            # Уведомления не критичны, поэтому не пробрасываем, только логируем
            self.handle_unexpected_error(
                e,
                UnexpectedAppError,
                message=f"Неожиданная ошибка при уведомлении администраторов: {e}",
                context={
                    "event": "admin_notification_unexpected_error",
                },
            )

    async def notify_dispatch_failure(
        self,
        slot_date: str,
        slot_time: str,
        error_details: str,
        traceback_str: str | None = None,
    ) -> None:
        """Уведомляет администраторов об ошибке рассылки Wednesday Frog.

        Args:
            slot_date: Дата слота рассылки.
            slot_time: Время слота рассылки.
            error_details: Детали ошибки.
            traceback_str: Трейсбек ошибки (опционально).
        """
        try:
            all_admins = await self._admins_repo.list_all_admins()
            if not all_admins:
                self.logger.warning(
                    "Нет администраторов для уведомления",
                    event="admin_notification_skipped",
                    status="warning",
                )
                return

            # Используем билдер для форматирования
            data = DispatchErrorData(
                slot_date=slot_date,
                slot_time=slot_time,
                error_details=error_details,
                traceback_str=traceback_str,
            )

            # Проверяем длину и выбираем формат
            if self._dispatch_builder.should_use_short(data):
                admin_message = self._dispatch_builder.build_short(data)
            else:
                admin_message = self._dispatch_builder.build(data)

            # Отправляем каждому админу
            for admin_id in all_admins:
                try:
                    await self._messaging.send_message(
                        chat_id=admin_id,
                        text=admin_message,
                    )

                    self.logger.info(
                        f"Уведомление о dispatch ошибке отправлено администратору {admin_id}",
                        event="admin_notification_sent",
                        status="ok",
                        admin_id=admin_id,
                    )
                except MessagingError as e:
                    # Ошибка отправки конкретному админу - логируем, но продолжаем
                    self.logger.error(
                        f"Не удалось отправить уведомление админу {admin_id}: {e}",
                        event="admin_notification_failed",
                        status="error",
                        admin_id=admin_id,
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
        except RepoError as e:
            # Ошибка получения списка админов - критично, но не падаем
            self.logger.error(
                f"Ошибка при получении списка администраторов: {e}",
                event="admin_repo_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
        except BaseException as e:
            # Неожиданная ошибка - логируем через handle_unexpected_error
            # Уведомления не критичны, поэтому не пробрасываем, только логируем
            self.handle_unexpected_error(
                e,
                UnexpectedAppError,
                message=f"Неожиданная ошибка при уведомлении администраторов: {e}",
                context={
                    "event": "admin_notification_unexpected_error",
                },
            )
