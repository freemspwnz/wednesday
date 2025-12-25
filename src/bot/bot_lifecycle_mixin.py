"""Миксин для общей логики жизненного цикла ботов."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from shared.protocols import ILogger

if TYPE_CHECKING:
    from telegram.ext import Application

    from bot.bot_lifecycle_manager import BotLifecycleManager
    from shared.bot_services import BotServices, SupportBotServices


class BotLifecycleMixin:
    """Миксин для общей логики жизненного цикла ботов.

    Инкапсулирует общую логику управления жизненным циклом:
    - Управление флагом is_running
    - Управление событием остановки _stop_event
    - Ожидание сигнала остановки
    - Базовая структура start() и stop()

    Используется как миксин для WednesdayBot и SupportBot для соблюдения принципа DRY.
    """

    # Эти атрибуты должны быть определены в классах, использующих миксин
    logger: ILogger
    lifecycle_manager: BotLifecycleManager
    application: Application
    is_running: bool
    _stop_event: asyncio.Event
    services: BotServices | SupportBotServices

    async def _wait_for_stop_signal(self) -> None:
        """Ожидает сигнала остановки через Event.

        Общая логика ожидания остановки для обоих ботов.
        Обрабатывает CancelledError для корректной обработки отмены задачи.

        Side Effects:
            - Блокируется до вызова _stop_event.set() в методе stop()
            - Устанавливает is_running в False при получении CancelledError
        """
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            self.logger.info("Получен сигнал отмены для основного цикла бота")
            self.is_running = False

    async def _initialize_lifecycle_state(self) -> None:
        """Инициализирует состояние жизненного цикла перед запуском.

        Устанавливает флаг запуска и сбрасывает event для нового цикла.
        Должен вызываться в начале метода start() после регистрации обработчиков.
        """
        self.is_running = True
        self._stop_event.clear()

    async def _stop_lifecycle(self) -> None:
        """Останавливает жизненный цикл бота.

        Устанавливает флаг остановки и разблокирует ожидание в start().
        Останавливает PTB Application через lifecycle manager.
        Должен вызываться в начале метода stop() после проверки is_running.

        Side Effects:
            - Устанавливает is_running в False
            - Разблокирует await self._stop_event.wait() в start()
            - Останавливает PTB Application
        """
        self.is_running = False
        self._stop_event.set()  # Разблокирует await self._stop_event.wait() in start()
        await self.lifecycle_manager.stop_application(self.application)

    async def _cleanup_resources(self) -> None:
        """Закрывает ресурсы бота.

        Гарантированно закрывает все ресурсы через services.cleanup().
        Должен вызываться в finally блоке метода stop().

        Side Effects:
            - Закрывает все ресурсы через services.cleanup()
            - Логирует результат операции
        """
        try:
            await self.services.cleanup()
            self.logger.info("Все ресурсы закрыты")
        except Exception as cleanup_error:
            self.logger.warning(f"Ошибка при cleanup ресурсов: {cleanup_error}")

    async def _send_lifecycle_notification(
        self,
        message_builder: Callable[[], str],
        chat_id: str | int | None,
        log_context: str = "жизненном цикле",
    ) -> None:
        """Отправляет уведомление о жизненном цикле бота.

        Унифицированный метод для отправки уведомлений о запуске/остановке бота.
        Используется в WednesdayBot и SupportBot для соблюдения принципа DRY.

        Args:
            message_builder: Функция, которая возвращает текст сообщения для отправки.
            chat_id: ID чата для отправки уведомления (может быть str, int или None).
            log_context: Контекст для логирования (например, "запуске", "остановке").

        Side Effects:
            - Вызывает message_builder() для получения текста сообщения.
            - Отправляет уведомление через admin_notification_service.notify_lifecycle_event().
            - Логирует ошибки отправки, но не прерывает выполнение.
        """
        if not self.services.admin_notification_service:
            return

        try:
            message = message_builder()
            chat_id_int = int(chat_id) if chat_id else None
            admin_chat_id_str = (
                str(self.services.settings.admin_chat_id)
                if self.services.settings and self.services.settings.admin_chat_id
                else None
            )

            await self.services.admin_notification_service.notify_lifecycle_event(
                message=message,
                chat_id=chat_id_int,
                admin_chat_id=admin_chat_id_str,
                exclude_chat_id=chat_id_int,
            )
        except Exception as send_error:
            self.logger.warning(f"Не удалось отправить сообщение о {log_context}: {send_error}")
