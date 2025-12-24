"""Application service для уведомления администраторов об ошибках."""

from __future__ import annotations

from shared.base.base_service import BaseService
from shared.base.exceptions import MessagingError, RepoError
from shared.protocols import IAdminsRepo, ILogger, IMessagingService

# Константы для форматирования сообщений
MAX_TRACE_LENGTH = 1500
MAX_MESSAGE_LENGTH = 4000
MAX_ERROR_DETAILS_LENGTH = 500


class AdminNotificationService(BaseService):
    """Сервис для уведомления администраторов об ошибках и событиях.

    Инкапсулирует логику форматирования и отправки уведомлений администраторам
    об ошибках генерации изображений, ошибках рассылки и других критических событиях.
    """

    def __init__(
        self,
        messaging_service: IMessagingService,
        admins_repo: IAdminsRepo,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис уведомлений.

        Args:
            messaging_service: Сервис для отправки сообщений.
            admins_repo: Репозиторий администраторов.
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._messaging = messaging_service
        self._admins_repo = admins_repo

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

            # Формируем сообщение
            admin_message = AdminNotificationService._format_generation_error_message(
                user_id=user_id,
                error_details=error_details,
                traceback_str=traceback_str,
            )

            # Отправляем каждому админу
            for admin_id in all_admins:
                try:
                    # Проверяем длину сообщения
                    if len(admin_message) > MAX_MESSAGE_LENGTH:
                        short_message = AdminNotificationService._format_short_error_message(
                            user_id=user_id,
                            error_details=error_details,
                        )
                        await self._messaging.send_message(
                            chat_id=admin_id,
                            text=short_message,
                        )
                    else:
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
        except (MemoryError, SystemExit, KeyboardInterrupt):
            # Системные ошибки пробрасываем выше без обёртки
            raise
        except BaseException as e:
            # Неожиданная ошибка
            self.logger.error(
                f"Неожиданная ошибка при уведомлении администраторов: {e}",
                event="admin_notification_unexpected_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )

    @staticmethod
    def _format_generation_error_message(
        user_id: int,
        error_details: str,
        traceback_str: str | None,
    ) -> str:
        """Форматирует сообщение об ошибке генерации.

        Args:
            user_id: ID пользователя.
            error_details: Детали ошибки.
            traceback_str: Трейсбек (опционально).

        Returns:
            Отформатированное сообщение.
        """
        message = (
            f"🔴 Ошибка генерации изображения по команде /frog\n\nПользователь: {user_id}\nДетали: {error_details}\n"
        )

        if traceback_str:
            # Обрезаем трейс до последних MAX_TRACE_LENGTH символов
            if len(traceback_str) > MAX_TRACE_LENGTH:
                traceback_str = "..." + traceback_str[-MAX_TRACE_LENGTH:]
            message += f"\nТрейс (последние {MAX_TRACE_LENGTH} символов):\n{traceback_str}\n"

        message += "\nПользователю отправлено дружелюбное сообщение и случайное изображение из архива."

        return message

    @staticmethod
    def _format_short_error_message(
        user_id: int,
        error_details: str,
    ) -> str:
        """Форматирует короткое сообщение об ошибке (без трейса).

        Args:
            user_id: ID пользователя.
            error_details: Детали ошибки.

        Returns:
            Короткое отформатированное сообщение.
        """
        return (
            "🔴 Ошибка при обработке команды /frog\n\n"
            f"Пользователь: {user_id}\n"
            f"Детали: {error_details[:MAX_ERROR_DETAILS_LENGTH]}\n\n"
            "⚠️ Полный трейс слишком длинный, смотрите логи.\n\n"
            "Пользователю отправлено дружелюбное сообщение и случайное изображение из архива."
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

            # Формируем сообщение
            admin_message = AdminNotificationService._format_dispatch_error_message(
                slot_date=slot_date,
                slot_time=slot_time,
                error_details=error_details,
                traceback_str=traceback_str,
            )

            # Отправляем каждому админу
            for admin_id in all_admins:
                try:
                    # Проверяем длину сообщения
                    if len(admin_message) > MAX_MESSAGE_LENGTH:
                        short_message = AdminNotificationService._format_short_dispatch_error_message(
                            slot_date=slot_date,
                            slot_time=slot_time,
                            error_details=error_details,
                        )
                        await self._messaging.send_message(
                            chat_id=admin_id,
                            text=short_message,
                        )
                    else:
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
        except (MemoryError, SystemExit, KeyboardInterrupt):
            # Системные ошибки пробрасываем выше без обёртки
            raise
        except BaseException as e:
            # Неожиданная ошибка
            self.logger.error(
                f"Неожиданная ошибка при уведомлении администраторов: {e}",
                event="admin_notification_unexpected_error",
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )

    @staticmethod
    def _format_dispatch_error_message(
        slot_date: str,
        slot_time: str,
        error_details: str,
        traceback_str: str | None,
    ) -> str:
        """Форматирует сообщение об ошибке рассылки.

        Args:
            slot_date: Дата слота рассылки.
            slot_time: Время слота рассылки.
            error_details: Детали ошибки.
            traceback_str: Трейсбек (опционально).

        Returns:
            Отформатированное сообщение.
        """
        message = f"🔴 Ошибка рассылки Wednesday Frog\n\nСлот: {slot_date} {slot_time}\nДетали: {error_details}\n"

        if traceback_str:
            # Обрезаем трейс до последних MAX_TRACE_LENGTH символов
            if len(traceback_str) > MAX_TRACE_LENGTH:
                traceback_str = "..." + traceback_str[-MAX_TRACE_LENGTH:]
            message += f"\nТрейс (последние {MAX_TRACE_LENGTH} символов):\n{traceback_str}\n"

        message += "\nПользователям отправлено fallback изображение из архива."

        return message

    @staticmethod
    def _format_short_dispatch_error_message(
        slot_date: str,
        slot_time: str,
        error_details: str,
    ) -> str:
        """Форматирует короткое сообщение об ошибке рассылки (без трейса).

        Args:
            slot_date: Дата слота рассылки.
            slot_time: Время слота рассылки.
            error_details: Детали ошибки.

        Returns:
            Короткое отформатированное сообщение.
        """
        return (
            f"🔴 Ошибка рассылки Wednesday Frog\n\n"
            f"Слот: {slot_date} {slot_time}\n"
            f"Детали: {error_details[:MAX_ERROR_DETAILS_LENGTH]}\n\n"
            "⚠️ Полный трейс слишком длинный, смотрите логи.\n\n"
            "Пользователям отправлено fallback изображение из архива."
        )
