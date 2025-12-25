"""
Основной класс Wednesday Frog Bot.
Объединяет все компоненты бота и управляет его жизненным циклом.
"""

import asyncio

from telegram.ext import Application

from app.bot_notification_builders import BotLifecycleNotificationBuilder
from bot.bot_application_factory import create_telegram_application
from bot.bot_chat_access_validator import BotChatAccessValidator
from bot.bot_error_handler import BotErrorHandler
from bot.bot_handlers_registry import BotHandlersRegistry
from bot.bot_lifecycle_manager import BotLifecycleManager
from bot.bot_lifecycle_mixin import BotLifecycleMixin
from bot.chat_event_handler import ChatEventHandler
from bot.handlers_admin import AdminHandlers
from bot.handlers_models import ModelHandlers
from bot.handlers_user import UserHandlers
from shared.bot_services import BotServices
from shared.config import BotTelegramConfig
from shared.protocols import ILogger

# Константы для магических чисел
TIMEOUT_MEDIUM_SECONDS = 30.0


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
    ) -> None:
        """Инициализирует WednesdayBot.

        Args:
            services: Контейнер сервисов бота (внедряется через DI).
            telegram_config: Конфигурация Telegram бота (внедряется через DI).
            logger: Экземпляр логгера для логирования операций (внедряется через DI).

        Создает и настраивает все компоненты основного бота:
        - Application для работы с Telegram API
        - ImageGenerator для генерации изображений
        - UsageTracker для отслеживания лимитов генераций
        - ChatsStore для управления списком чатов
        - PromptCache, UserStateCache, RateLimiter для работы с Redis
        - UserHandlers, AdminHandlers, ModelHandlers для обработки команд

        Инициализирует все необходимые сервисы и готовит бота к запуску.
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

        # Создаем обработчики команд
        self.logger.info("Создание специализированных наборов хендлеров")
        # Узкоспециализированные наборы для регистрации в PTB по зонам ответственности
        self.user_handlers: UserHandlers = UserHandlers(self.services, logger=self.logger)
        # Админские и пользовательские команды должны разделять общее состояние (лимиты, хранилища),
        # поэтому используем единый контейнер сервисов.
        self.admin_handlers: AdminHandlers = AdminHandlers(self.services, logger=self.logger)
        self.model_handlers: ModelHandlers = ModelHandlers(self.services, logger=self.logger)

        # ID чата для отправки сообщений
        self.chat_id: str | None = telegram_config.chat_id
        self.logger.info(f"Chat ID установлен: {self.chat_id}")

        # Инициализация компонентов для управления жизненным циклом
        self.error_handler = BotErrorHandler(self.logger)
        self.chat_validator = BotChatAccessValidator(self.logger, timeout=TIMEOUT_MEDIUM_SECONDS)
        self.lifecycle_manager = BotLifecycleManager(self.logger)
        self.chat_event_handler = ChatEventHandler(
            services=self.services,
            bot=self.application.bot,
            logger=self.logger,
        )

        # Инициализация регистратора обработчиков
        self.handlers_registry = BotHandlersRegistry(
            application=self.application,
            user_handlers=self.user_handlers,
            admin_handlers=self.admin_handlers,
            model_handlers=self.model_handlers,
            chat_event_handler=self.chat_event_handler,
            error_handler=self.error_handler,
            logger=self.logger,
        )

        # Флаг состояния бота
        self.is_running: bool = False
        # Event для ожидания сигнала остановки (вместо busy-wait цикла)
        self._stop_event = asyncio.Event()

        # Задача планировщика (инициализируется при старте)

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

    async def start(self) -> None:
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

        try:
            # Настраиваем обработчики
            self.handlers_registry.register_all()

            # Настраиваем и запускаем планировщик (только если используется старый планировщик)

            # Проверяем доступность чата перед отправкой сообщения
            if self.chat_id:
                await self.chat_validator.validate_chat_access(self.application.bot, self.chat_id)

            # Запускаем PTB Application через lifecycle manager
            await self.lifecycle_manager.start_application(self.application)

            # Отправляем уведомление о запуске
            await self._send_lifecycle_notification(
                BotLifecycleNotificationBuilder.build_startup_message,
                self.chat_id,
                log_context="запуске",
            )

            # Celery используется для планирования задач
            self.logger.info("Celery используется для планирования задач")

            # Инициализируем состояние жизненного цикла
            await self._initialize_lifecycle_state()

            # Ожидаем сигнала остановки через Event
            await self._wait_for_stop_signal()

        except Exception as e:
            self.logger.error(f"Ошибка при запуске бота: {e}")
            raise

    async def stop(self) -> None:
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
        # Защита от повторных вызовов
        if not self.is_running:
            self.logger.info("Бот уже остановлен или остановка уже начата")
            return

        self.logger.info("Останавливаю Wednesday Bot")

        try:
            # Останавливаем жизненный цикл
            await self._stop_lifecycle()

            # Отправляем уведомление об остановке
            if not self._stop_message_sent:
                await self._send_lifecycle_notification(
                    BotLifecycleNotificationBuilder.build_shutdown_message,
                    self.chat_id,
                    log_context="остановке",
                )
                self._stop_message_sent = True

            self.logger.info("Бот успешно остановлен")

        except Exception as e:
            self.logger.error(f"Ошибка при остановке бота: {e}")
        finally:
            # Гарантированное закрытие ресурсов (всегда выполняется)
            await self._cleanup_resources()

            # Дополнительно защитимся от повторных отправок в жизненном цикле объекта
            self._stop_message_sent = True
