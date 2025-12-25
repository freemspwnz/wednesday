"""
Основной класс Wednesday Frog Bot.
Объединяет все компоненты бота и управляет его жизненным циклом.
"""

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

from telegram.ext import Application

from app.bot_notification_builders import BotLifecycleNotificationBuilder
from bot.bot_application_factory import create_telegram_application
from bot.bot_lifecycle_mixin import BotLifecycleMixin
from shared.bot_services import BotServices
from shared.config import BotTelegramConfig
from shared.protocols import ILogger

if TYPE_CHECKING:
    from infra.container import BotComponents


class WednesdayBot(BotLifecycleMixin):
    """Основной класс Telegram бота для отправки изображений жабы каждую среду.

    WednesdayBot - это полнофункциональный Telegram бот, который:
    - Генерирует изображения жабы с помощью нейросети Kandinsky
    - Автоматически отправляет изображения в настроенные чаты по расписанию (среды)
    - Обрабатывает команды пользователей и администраторов
    - Управляет лимитами генераций и rate limiting
    - Отслеживает метрики производительности
    - Интегрируется с Redis для кэширования и хранения состояния
    - Использует Celery для планирования и выполнения автоматических отправок

    Бот управляет жизненным циклом всех компонентов: от инициализации до
    корректной остановки с освобождением ресурсов.
    """

    def __init__(
        self,
        services: BotServices,
        telegram_config: BotTelegramConfig,
        logger: ILogger,
        components: BotComponents,
    ) -> None:
        """Инициализирует WednesdayBot.

        Args:
            services: Контейнер сервисов бота (внедряется через DI).
            telegram_config: Конфигурация Telegram бота (внедряется через DI).
            logger: Экземпляр логгера для логирования операций (внедряется через DI).
            components: Контейнер компонентов бота (внедряется через DI).

        Все компоненты (handlers, validators, managers) создаются в composition root
        (infra/container.py) и передаются через DI для соблюдения принципа SRP.
        """
        self.logger = logger
        self.logger.info("Начало инициализации WednesdayBot")

        # Создаем Application через фабрику
        self.logger.info("Создание Application через фабрику")
        self.application: Application = create_telegram_application(telegram_config)

        # Сервисы внедряются через конструктор (DI)
        self.services = services
        # bot_controller устанавливается в composition root (container.py) для избежания циклической зависимости
        # Флаг, чтобы избежать дублирующих сообщений об остановке
        self._stop_message_sent: bool = False

        # Компоненты внедряются через конструктор (DI) - создаются в composition root
        # Тип гарантирован через типизацию параметра конструктора
        self.user_handlers = components.user_handlers
        self.admin_handlers = components.admin_handlers
        self.model_handlers = components.model_handlers
        self.error_handler = components.error_handler
        self.chat_validator = components.chat_validator
        self.lifecycle_manager = components.lifecycle_manager
        self.chat_event_handler = components.chat_event_handler
        self.handlers_registry = components.handlers_registry

        # ID чата для отправки сообщений
        self.chat_id: str | None = telegram_config.chat_id
        self.logger.info(f"Chat ID установлен: {self.chat_id}")

        # Флаг состояния бота
        self.is_running: bool = False
        # Event для ожидания сигнала остановки (вместо busy-wait цикла)
        self._stop_event = asyncio.Event()

        self.logger.info("WednesdayBot успешно инициализирован")

    async def send_wednesday_frog(self, slot_time: str | None = None) -> None:
        """Основная функция для отправки изображения жабы по расписанию.

        Делегирует выполнение рассылки в DispatchService, который автоматически
        определяет слот времени, если он не указан.

        Args:
            slot_time: Опциональное время слота в формате "HH:MM" для идентификации
                отправки. Если None, определяется автоматически в DispatchService
                на основе текущего времени и настроенных времен отправки.

        Side Effects:
            - Вызывает DispatchService.send_wednesday_frog_with_auto_slot() для выполнения рассылки.
            - DispatchService координирует генерацию изображения, отправку в чаты,
              использование fallback при ошибках и уведомление администраторов.
        """
        # Проверяем наличие dispatch_service (доступен только в BotServices, не в SupportBotServices)
        dispatch_service = getattr(self.services, "dispatch_service", None)
        if dispatch_service is None:
            self.logger.error("DispatchService недоступен, пропускаю рассылку")
            return

        await dispatch_service.send_wednesday_frog_with_auto_slot(
            slot_time=slot_time,
            main_chat_id=self.chat_id,
        )

    async def start(
        self,
        notification_builder: Callable[[], str] | None = None,
        pre_startup_hook: Callable[[], None] | None = None,
    ) -> None:
        """Запускает бота и планировщик задач.

        Важно:
            Вместо стандартного `application.run_polling()` используется
            явная последовательность:

                `initialize() -> start() -> updater.start_polling() ->
                кастомный цикл while self.is_running`.

            Этот legacy‑паттерн выбран осознанно и критичен для текущей
            архитектуры:

            - интеграция с резервным `SupportBot`, который использует тот же
              Telegram‑токен и должен запускаться и останавливаться
              согласованно с основным ботом;
            - управление жизненным циклом из внешнего супервизора
              (CeleryServices, команды /stop и управление из других процессов);
            - возможность «мягкой» остановки: отправка финальных сообщений,
              обновление статусных сообщений SupportBot и корректный shutdown
              PTB‑приложения (`application.stop()` + `application.shutdown()`).

            При переводе на `application.run_polling()` или другую схему
            запуска необходимо пересмотреть:

            - логику взаимодействия `WednesdayBot` и `SupportBot`;
            - ожидания Celery‑слоя относительно управления жизненным циклом;
            - порядок вызовов `initialize/start/stop/shutdown` и обработку
              статусных сообщений в чатах.

        Side Effects:
            - Настраивает обработчики команд через handlers_registry.register_all().
            - Инициализирует приложение через application.initialize().
            - Запускает polling через updater.start_polling().
            - Сохраняет сервисы в bot_data для доступа обработчиков.
            - Проверяет доступность чата через chat_validator.validate_chat_access().
            - Отправляет сообщения о запуске в CHAT_ID и админам.
            - Редактирует статусные сообщения от SupportBot (если есть).
            - Запускает планировщик в фоновой задаче (если включен).
            - Запускает основной цикл ожидания.

        Raises:
            Exception: Если не удалось запустить бота после всех попыток ретраев.
        """
        self.logger.info("Запускаю Wednesday Bot (боевой режим с планировщиком)")

        def _validate_configuration() -> None:
            """Валидация конфигурации слотов перед запуском."""
            # Валидация конфигурации слотов основана на настройках, а не на внутреннем состоянии планировщика.
            settings = self.services.settings
            configured_times = settings.scheduler_send_times
            # Таймзона берется из AppSettings через DI
            timezone = settings.scheduler_tz or "Europe/Moscow"
            # День недели по умолчанию - среда (2), если не задан в настройках
            # Примечание: wednesday_day не доступен в AppSettings, используем значение по умолчанию
            wednesday_day = 2  # 2 = среда (0 = понедельник)

            self.logger.info(
                "Используется Celery для планирования задач: "
                f"день недели={wednesday_day}, времена={configured_times}, TZ={timezone}",
            )

            if not configured_times:
                self.logger.error("⚠️  Не заданы времена отправки! Используются значения по умолчанию.")

            # Celery используется для планирования задач
            self.logger.info("Celery используется для планирования задач")

        # Используем переданный notification_builder или значение по умолчанию
        if notification_builder is None:
            notification_builder = BotLifecycleNotificationBuilder.build_startup_message

        # Используем переданный pre_startup_hook или валидацию конфигурации
        if pre_startup_hook is None:
            pre_startup_hook = _validate_configuration
        else:
            # Если передан внешний hook, выполняем его после валидации
            original_hook = pre_startup_hook

            def _combined_hook() -> None:
                _validate_configuration()
                original_hook()

            pre_startup_hook = _combined_hook

        # Выполняем общую последовательность запуска через миксин
        await super().start(
            notification_builder=notification_builder,
            pre_startup_hook=pre_startup_hook,
        )

    async def stop(
        self,
        notification_builder: Callable[[], str] | None = None,
        chat_id: str | int | None = None,
        pre_stop_hook: Callable[[], None] | None = None,
        post_stop_hook: Callable[[], None] | None = None,
    ) -> None:
        """Останавливает бота и планировщик задач.

        Корректно завершает работу бота: останавливает планировщик, polling,
        отправляет уведомления об остановке и освобождает все ресурсы.
        Защищен от повторных вызовов через проверку is_running.

        Side Effects:
            - Устанавливает флаг is_running в False.
            - Останавливает PTB Application через lifecycle_manager.stop_application().
            - Отправляет сообщения об остановке в CHAT_ID и админам.
            - Гарантированно закрывает все ресурсы через services.cleanup() в finally блоке.
        """
        self.logger.info("Останавливаю Wednesday Bot")

        # Используем переданный chat_id или значение по умолчанию
        if chat_id is None:
            chat_id = self.chat_id

        # Определяем функцию для отправки уведомления с проверкой флага
        if notification_builder is None and not self._stop_message_sent:
            notification_builder = BotLifecycleNotificationBuilder.build_shutdown_message

        def _post_stop() -> None:
            """Специфичная логика после остановки: защита от повторных отправок."""
            # Дополнительно защитимся от повторных отправок в жизненном цикле объекта
            self._stop_message_sent = True
            # Выполняем переданный post_stop_hook, если есть
            if post_stop_hook:
                post_stop_hook()

        # Выполняем общую последовательность остановки через миксин
        await super().stop(
            notification_builder=notification_builder,
            chat_id=chat_id,
            pre_stop_hook=pre_stop_hook,
            post_stop_hook=_post_stop,
        )

        # Устанавливаем флаг после успешной отправки (если было отправлено)
        if not self._stop_message_sent:
            self._stop_message_sent = True
