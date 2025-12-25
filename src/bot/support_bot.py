"""
Резервный (поддерживающий) бот, который включается при остановке основного.
"""

import asyncio
from typing import TYPE_CHECKING

from telegram.ext import Application

from app.bot_notification_builders import BotLifecycleNotificationBuilder
from bot.bot_application_factory import create_telegram_application
from bot.bot_lifecycle_mixin import BotLifecycleMixin
from shared.bot_services import SupportBotServices
from shared.config import BotTelegramConfig
from shared.protocols import IHandlersRegistry, ILogger

if TYPE_CHECKING:
    from bot.support_bot_handlers_registry import SupportBotHandlersRegistry
    from infra.container import SupportBotComponents


class SupportBot(BotLifecycleMixin):
    """Резервный бот-поддержка.

    SupportBot работает когда основной WednesdayBot остановлен и обеспечивает
    базовую функциональность для администраторов:
    - Команда /start для запуска основного бота
    - Команда /log для получения логов
    - Команда /help для справки
    - Обработка неизвестных команд с сообщением о техработах

    Важно: SupportBot никогда не должен работать одновременно с основным ботом,
    так как они используют один и тот же Telegram токен и будут конфликтовать
    при попытке получить обновления (getUpdates).

    Использует минимальный SupportBotServices с только необходимыми зависимостями.
    Обработчики команд вынесены в отдельный класс SupportBotHandlers для соблюдения SRP.
    """

    def __init__(
        self,
        services: SupportBotServices,
        telegram_config: BotTelegramConfig,
        logger: ILogger,
        components: SupportBotComponents,
    ) -> None:
        """Инициализирует SupportBot.

        Создает экземпляр резервного бота, который работает когда основной бот остановлен.
        SupportBot предоставляет базовую функциональность: команды /help, /log и /start
        для запуска основного бота.

        Args:
            services: Контейнер сервисов для SupportBot (внедряется через DI).
            telegram_config: Конфигурация Telegram бота (внедряется через DI).
            logger: Экземпляр логгера для логирования операций (внедряется через DI).
            components: Контейнер компонентов бота (внедряется через DI).

        Raises:
            ValueError: Если services равен None.
        """
        if services is None:
            raise ValueError("services не может быть None. Передайте SupportBotServices через Dependency Injection.")

        # Сохраняем зависимости
        self.logger = logger
        self.services = services

        # Создаем Application через фабрику
        self.logger.info("Создание Application через фабрику")
        self.application: Application = create_telegram_application(telegram_config)
        self.is_running: bool = False
        # Event для ожидания сигнала остановки (вместо busy-wait цикла)
        self._stop_event = asyncio.Event()

        # Компоненты внедряются через конструктор (DI) - создаются в composition root
        # Тип гарантирован через типизацию параметра конструктора
        self.error_handler = components.error_handler
        self.chat_validator = components.chat_validator
        self.lifecycle_manager = components.lifecycle_manager
        self.chat_event_handler = components.chat_event_handler
        # handlers_registry может быть None, если создается после SupportBot (из-за циклической зависимости)
        self.handlers_registry: IHandlersRegistry | None = components.handlers_registry

        # ID чата для отправки сообщений (если задан в конфигурации)
        self.chat_id: str | None = telegram_config.chat_id

    def set_handlers_registry(self, handlers_registry: SupportBotHandlersRegistry) -> None:
        """Устанавливает handlers_registry после создания бота.

        Используется для разрешения циклической зависимости:
        SupportBotHandlersRegistry требует support_bot, который еще не создан.

        Args:
            handlers_registry: Регистратор обработчиков для SupportBot.
        """
        self.handlers_registry = handlers_registry

    async def start(self) -> None:
        """Запускает SupportBot и начинает обработку команд.

        Инициализирует приложение, запускает polling через BotLifecycleManager
        и отправляет уведомления администраторам о запуске SupportBot.

        Side Effects:
            - Запускает PTB Application через lifecycle_manager.start_application() с warmup.
            - Отправляет уведомления администраторам о запуске SupportBot.
            - Запускает основной цикл ожидания.

        Raises:
            Exception: Если не удалось запустить приложение после всех попыток.
        """
        self.logger.info("Запуск бота-поддержки (SupportBot)")

        # Выполняем общую последовательность запуска через миксин
        await self._execute_startup_sequence(
            notification_builder=BotLifecycleNotificationBuilder.build_support_startup_message,
            log_context="запуске",
        )

        self.logger.info("SupportBot основной цикл завершен")

    async def stop(self) -> None:
        """Останавливает SupportBot и освобождает ресурсы.

        Корректно завершает работу бота, останавливает polling и отправляет
        уведомления администраторам об остановке.

        Side Effects:
            - Устанавливает флаг is_running в False.
            - Отправляет уведомления администраторам об остановке.
            - Останавливает PTB Application через lifecycle_manager.stop_application().
            - Гарантированно закрывает ресурсы через services.cleanup() в finally блоке.
        """
        if not self.is_running:
            return

        self.logger.info("Остановка бота-поддержки")

        try:
            # Останавливаем жизненный цикл
            await self._stop_lifecycle()

            # Отправляем уведомление об остановке
            await self._send_lifecycle_notification(
                BotLifecycleNotificationBuilder.build_support_shutdown_message,
                self.chat_id,
                log_context="остановке",
            )

            self.logger.info("SupportBot успешно остановлен")

        except Exception as e:
            self.logger.error(f"Ошибка при остановке SupportBot: {e}", exc_info=True)
        finally:
            # Гарантированное закрытие ресурсов (всегда выполняется)
            await self._cleanup_resources()
