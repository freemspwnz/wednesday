"""Менеджер жизненного цикла PTB Application."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from telegram.ext import Application, Update

from shared.protocols import ILogger

if TYPE_CHECKING:
    pass

# Константы для retry логики
MAX_POLLING_ATTEMPTS = 3
LAST_POLLING_ATTEMPT_INDEX = 2


class BotLifecycleManager:
    """Управляет жизненным циклом PTB Application.

    Обеспечивает корректный запуск и остановку PTB Application с retry логикой.
    """

    def __init__(self, logger: ILogger) -> None:
        """Инициализирует менеджер жизненного цикла.

        Args:
            logger: Экземпляр логгера.
        """
        self._logger = logger

    async def start_application(
        self,
        application: Application,
        enable_warmup: bool = False,
    ) -> None:
        """Запускает PTB Application с retry логикой.

        Выполняет инициализацию, опциональный warmup, запуск и начало polling
        с повторными попытками при сетевых ошибках.

        Args:
            application: Экземпляр PTB Application для запуска.
            enable_warmup: Если True, выполняет warmup через bot.get_me() после initialize().

        Raises:
            Exception: Если не удалось запустить после всех попыток.
        """
        # Инициализируем приложение асинхронно
        await application.initialize()

        # Опциональный warmup для гарантированного установления контекста
        if enable_warmup:
            try:
                _ = await application.bot.get_me()
                self._logger.info("Warmup get_me() успешно выполнен")
            except Exception as warmup_err:
                # Не фейлим старт из-за warmup; просто залогируем
                self._logger.warning(f"Warmup get_me() не удался: {warmup_err}", exc_info=True)

        # Ретраи запуска сети (start + polling)
        delay = 3
        for attempt in range(MAX_POLLING_ATTEMPTS):
            try:
                await application.start()
                updater = application.updater
                if updater:
                    await updater.start_polling(
                        allowed_updates=Update.ALL_TYPES,
                        drop_pending_updates=True,
                    )
                self._logger.info("PTB Application успешно запущено")
                break
            except Exception as e:
                self._logger.warning(
                    f"Не удалось запустить polling (попытка {attempt + 1}/{MAX_POLLING_ATTEMPTS}): {e}",
                )
                if attempt == LAST_POLLING_ATTEMPT_INDEX:
                    self._logger.error("Не удалось запустить PTB Application после всех попыток")
                    raise
                await asyncio.sleep(delay)
                delay *= 2

    async def stop_application(self, application: Application) -> None:
        """Останавливает PTB Application корректно.

        Выполняет остановку updater, затем application.stop() и application.shutdown()
        для корректного освобождения ресурсов.

        Args:
            application: Экземпляр PTB Application для остановки.
        """
        # Безопасная остановка updater'а
        try:
            if hasattr(application, "updater") and application.updater:
                await application.updater.stop()
                self._logger.info("PTB Updater остановлен")
        except Exception as e:
            self._logger.warning(f"Ошибка при остановке updater'а: {e}")

            # Небольшая пауза, чтобы освободить соединения пула
            await asyncio.sleep(0.2)

        # Безопасная остановка приложения
        try:
            await application.stop()
            self._logger.info("PTB Application остановлено")
        except Exception as e:
            self._logger.warning(f"Ошибка при остановке приложения: {e}")

        # Финальный шаг жизненного цикла PTB: корректный shutdown приложения
        try:
            await application.shutdown()
            self._logger.info("PTB Application shutdown завершен")
        except Exception as e:
            self._logger.warning(f"Ошибка при shutdown приложения: {e}")
