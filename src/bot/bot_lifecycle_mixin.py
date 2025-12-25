"""Миксин для общей логики жизненного цикла ботов."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from shared.protocols import IChatValidator, IHandlersRegistry, ILogger

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
    handlers_registry: IHandlersRegistry | None
    chat_validator: IChatValidator
    chat_id: str | int | None

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

    async def _execute_startup_sequence(
        self,
        notification_builder: Callable[[], str],
        log_context: str = "запуске",
    ) -> None:
        """Выполняет общую последовательность запуска бота.

        Унифицированный метод для выполнения общей последовательности запуска,
        используемый в WednesdayBot и SupportBot для соблюдения принципа DRY.

        Последовательность:
        1. Регистрация обработчиков
        2. Валидация доступа к чату (если chat_id задан)
        3. Запуск PTB Application
        4. Отправка уведомления о запуске
        5. Инициализация состояния жизненного цикла
        6. Ожидание сигнала остановки

        Args:
            notification_builder: Функция, которая возвращает текст сообщения для отправки.
            log_context: Контекст для логирования (например, "запуске").

        Side Effects:
            - Регистрирует все обработчики через handlers_registry.register_all()
            - Проверяет доступность чата через chat_validator.validate_chat_access()
            - Запускает PTB Application через lifecycle_manager.start_application()
            - Отправляет уведомление о запуске через _send_lifecycle_notification()
            - Инициализирует состояние жизненного цикла через _initialize_lifecycle_state()
            - Ожидает сигнала остановки через _wait_for_stop_signal()

        Raises:
            Exception: Если не удалось выполнить какой-либо шаг последовательности.
        """
        # 1. Регистрация обработчиков
        if self.handlers_registry is None:
            raise RuntimeError("handlers_registry не установлен. Убедитесь, что он установлен перед вызовом start().")
        self.handlers_registry.register_all()

        # 2. Валидация доступа к чату (если chat_id задан)
        if self.chat_id:
            chat_id_str = str(self.chat_id) if isinstance(self.chat_id, int) else self.chat_id
            await self.chat_validator.validate_chat_access(self.application.bot, chat_id_str)

        # 3. Запуск PTB Application
        await self.lifecycle_manager.start_application(self.application)

        # 4. Отправка уведомления о запуске
        await self._send_lifecycle_notification(
            notification_builder,
            self.chat_id,
            log_context=log_context,
        )

        # 5. Инициализация состояния жизненного цикла
        await self._initialize_lifecycle_state()

        # 6. Ожидание сигнала остановки
        await self._wait_for_stop_signal()

    async def start(
        self,
        notification_builder: Callable[[], str],
        pre_startup_hook: Callable[[], None] | None = None,
    ) -> None:
        """Универсальный метод запуска для обоих ботов.

        Выполняет общую последовательность запуска через _execute_startup_sequence.
        Позволяет выполнить специфичную логику перед запуском через pre_startup_hook.

        Args:
            notification_builder: Функция, которая возвращает текст сообщения для отправки.
            pre_startup_hook: Опциональная функция для выполнения специфичной логики перед запуском
                (например, валидация конфигурации).

        Side Effects:
            - Вызывает pre_startup_hook() если он задан
            - Выполняет общую последовательность запуска через _execute_startup_sequence()

        Raises:
            Exception: Если не удалось запустить бота после всех попыток ретраев.
        """
        if pre_startup_hook:
            pre_startup_hook()

        try:
            await self._execute_startup_sequence(
                notification_builder=notification_builder,
                log_context="запуске",
            )
        except Exception as e:
            self.logger.error(f"Ошибка при запуске бота: {e}")
            raise

    async def stop(
        self,
        notification_builder: Callable[[], str] | None = None,
        chat_id: str | int | None = None,
        pre_stop_hook: Callable[[], None] | None = None,
        post_stop_hook: Callable[[], None] | None = None,
    ) -> None:
        """Универсальный метод остановки для обоих ботов.

        Выполняет общую последовательность остановки с возможностью выполнения
        специфичной логики через хуки.

        Args:
            notification_builder: Опциональная функция для построения сообщения об остановке.
            chat_id: ID чата для отправки уведомления об остановке (если не указан, используется self.chat_id).
            pre_stop_hook: Опциональная функция для выполнения специфичной логики перед остановкой.
            post_stop_hook: Опциональная функция для выполнения специфичной логики после остановки
                (но до cleanup ресурсов).

        Side Effects:
            - Устанавливает флаг is_running в False.
            - Останавливает PTB Application через lifecycle_manager.stop_application().
            - Отправляет уведомление об остановке (если notification_builder задан).
            - Гарантированно закрывает все ресурсы через services.cleanup() в finally блоке.
        """
        # Защита от повторных вызовов
        if not self.is_running:
            self.logger.info("Бот уже остановлен или остановка уже начата")
            return

        # Выполняем специфичную логику перед остановкой
        if pre_stop_hook:
            pre_stop_hook()

        try:
            # Останавливаем жизненный цикл
            await self._stop_lifecycle()

            # Отправляем уведомление об остановке (если задано)
            if notification_builder:
                target_chat_id = chat_id if chat_id is not None else self.chat_id
                await self._send_lifecycle_notification(
                    notification_builder,
                    target_chat_id,
                    log_context="остановке",
                )

            # Выполняем специфичную логику после остановки
            if post_stop_hook:
                post_stop_hook()

            self.logger.info("Бот успешно остановлен")

        except Exception as e:
            self.logger.error(f"Ошибка при остановке бота: {e}", exc_info=True)
        finally:
            # Гарантированное закрытие ресурсов (всегда выполняется)
            await self._cleanup_resources()
