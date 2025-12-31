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
from shared.protocols.infrastructure import ILogger
from shared.protocols.messaging import IMessagingService
from shared.protocols.repositories import IAdminsRepo


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

    async def notify_lifecycle_event(
        self,
        message: str,
        chat_id: int | None = None,
        admin_chat_id: str | None = None,
        exclude_chat_id: int | None = None,
    ) -> None:
        """Отправляет уведомление о жизненном цикле бота.

        Отправляет сообщение:
        1. В основной чат (chat_id), если задан.
        2. Администраторам (через admin_chat_id или всем из репозитория).

        Args:
            message: Текст сообщения для отправки.
            chat_id: ID основного чата для отправки уведомления (опционально).
            admin_chat_id: ID админ-чата (если задан, отправляет туда вместо всех админов).
            exclude_chat_id: ID чата для исключения из отправки админам (чтобы избежать дубля с основным чатом).
        """
        # Отправляем в основной чат
        if chat_id:
            try:
                await self._messaging.send_message(
                    chat_id=chat_id,
                    text=message,
                )
                self.logger.info(f"Lifecycle уведомление отправлено в основной чат {chat_id}")
            except MessagingError as e:
                self.logger.warning(f"Не удалось отправить lifecycle уведомление в основной чат {chat_id}: {e}")

        # Отправляем администраторам
        await self.notify_lifecycle_to_admins(
            message=message,
            admin_chat_id=admin_chat_id,
            exclude_chat_id=exclude_chat_id,
        )

    async def notify_lifecycle_to_admins(
        self,
        message: str,
        admin_chat_id: str | None = None,
        exclude_chat_id: int | None = None,
    ) -> None:
        """Отправляет уведомление о жизненном цикле бота администраторам.

        Отправляет сообщение администраторам в следующем порядке:
        1. Если задан admin_chat_id и он не исключён - отправляет туда и завершает.
        2. Иначе отправляет всем админам из репозитория, исключая exclude_chat_id.

        Args:
            message: Текст сообщения для отправки.
            admin_chat_id: ID админ-чата (если задан, отправляет туда вместо всех админов).
            exclude_chat_id: ID чата для исключения (чтобы избежать дубля с основным чатом).
        """
        try:
            exclude_ids: set[int] = {exclude_chat_id} if exclude_chat_id else set()

            # Если задан admin_chat_id и он не исключён - отправляем туда
            if admin_chat_id:
                try:
                    admin_chat_id_int = int(str(admin_chat_id))
                    if admin_chat_id_int not in exclude_ids:
                        await self._messaging.send_message(
                            chat_id=admin_chat_id_int,
                            text=message,
                        )
                        self.logger.info(
                            f"Lifecycle уведомление отправлено в админ-чат {admin_chat_id_int}",
                            event="admin_lifecycle_notification_sent",
                            status="ok",
                            admin_chat_id=admin_chat_id_int,
                        )
                        return  # Отправили в админ-чат, больше не отправляем
                except (ValueError, MessagingError) as e:
                    # Если не удалось отправить в admin_chat_id, продолжаем отправку всем админам
                    self.logger.warning(
                        f"Не удалось отправить в админ-чат {admin_chat_id}: {e}",
                        event="admin_chat_send_failed",
                        status="warning",
                        error_type=type(e).__name__,
                    )

            # Отправляем всем админам из репозитория (исключая exclude_ids)
            all_admins = await self._admins_repo.list_all_admins()
            if not all_admins:
                self.logger.warning(
                    "Нет администраторов для уведомления",
                    event="admin_lifecycle_notification_skipped",
                    status="warning",
                )
                return

            for admin_id in all_admins:
                if admin_id in exclude_ids:
                    continue
                try:
                    await self._messaging.send_message(
                        chat_id=admin_id,
                        text=message,
                    )
                    self.logger.info(
                        f"Lifecycle уведомление отправлено администратору {admin_id}",
                        event="admin_lifecycle_notification_sent",
                        status="ok",
                        admin_id=admin_id,
                    )
                except MessagingError as e:
                    # Ошибка отправки конкретному админу - логируем, но продолжаем
                    self.logger.error(
                        f"Не удалось отправить lifecycle уведомление админу {admin_id}: {e}",
                        event="admin_lifecycle_notification_failed",
                        status="error",
                        admin_id=admin_id,
                        error_type=type(e).__name__,
                        error_message=str(e),
                    )
        except RepoError as e:
            # Ошибка получения списка админов - критично, но не падаем
            self.logger.error(
                f"Ошибка при получении списка администраторов для lifecycle уведомления: {e}",
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
                message=f"Неожиданная ошибка при отправке lifecycle уведомления администраторам: {e}",
                context={
                    "event": "admin_lifecycle_notification_unexpected_error",
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
