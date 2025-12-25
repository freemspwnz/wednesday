"""Миксин для общей логики жизненного цикла ботов."""

from __future__ import annotations

import asyncio
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
        Должен вызываться в начале метода start() после setup_handlers().
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
