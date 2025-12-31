"""Класс WednesdayBot для управления жизненным циклом Telegram бота.

Отвечает исключительно за Telegram-часть: регистрацию хендлеров и запуск polling.
Не знает про базу данных или Redis напрямую - все зависимости получает через Container.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram.ext import Application

from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    from infra.new_container import Container


class WednesdayBot:
    """Класс для управления жизненным циклом Telegram бота.

    Отвечает только за Telegram-часть:
    - Регистрацию хендлеров через Container
    - Запуск и остановку polling
    - Управление Application

    Не знает про базу данных, Redis или другие инфраструктурные компоненты
    напрямую - все зависимости получает через Container.
    """

    def __init__(
        self,
        application: Application,
        container: Container,
        logger: ILogger,
    ) -> None:
        """Инициализирует WednesdayBot.

        Args:
            application: PTB Application для управления ботом.
            container: Контейнер зависимостей для создания хендлеров.
            logger: Логгер для логирования операций.
        """
        self._application = application
        self._container = container
        self._logger = logger

    async def run(self) -> None:
        """Запускает бота в режиме polling.

        Последовательность действий:
        1. Создает регистратор хендлеров через container
        2. Регистрирует все хендлеры
        3. Запускает polling

        Side Effects:
            - Регистрирует все обработчики команд через registry.register_all()
            - Запускает бесконечный цикл polling через application.run_polling()
        """
        self._logger.info(
            "Инициализация регистратора хендлеров",
            event="bot_init_handlers_registry",
            status="started",
        )
        registry = self._container.build_handlers_registry(self._application)
        self._logger.debug(
            "Регистратор хендлеров создан",
            event="bot_handlers_registry_created",
            status="ok",
        )

        self._logger.info(
            "Регистрация всех хендлеров",
            event="bot_register_handlers",
            status="started",
        )
        registry.register_all()
        self._logger.info(
            "Все хендлеры зарегистрированы",
            event="bot_handlers_registered",
            status="ok",
        )

        self._logger.info(
            "Запуск polling режима",
            event="bot_start_polling",
            status="started",
        )
        await self._application.run_polling()

    async def stop(self) -> None:
        """Корректно завершает работу бота.

        Останавливает Application и освобождает ресурсы Telegram API.

        Side Effects:
            - Останавливает polling через application.stop()
            - Закрывает соединения через application.shutdown()
        """
        self._logger.info(
            "Остановка бота",
            event="bot_stop",
            status="started",
        )
        try:
            await self._application.stop()
            await self._application.shutdown()
            self._logger.info(
                "Бот успешно остановлен",
                event="bot_stopped",
                status="ok",
            )
        except Exception as e:
            self._logger.error(
                "Ошибка при остановке бота",
                event="bot_stop_error",
                status="error",
                error=str(e),
            )
            raise
