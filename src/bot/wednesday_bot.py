"""
Основной класс Wednesday Frog Bot.
Объединяет все компоненты бота и управляет его жизненным циклом.
"""

import asyncio
from typing import Any

from telegram.ext import Application, ChatMemberHandler, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from bot.bot_chat_access_validator import BotChatAccessValidator
from bot.bot_error_handler import BotErrorHandler
from bot.bot_lifecycle_manager import BotLifecycleManager
from bot.bot_state_coordinator import BotStateCoordinator, BotStateData
from bot.chat_event_handler import ChatEventHandler
from bot.handlers_admin import AdminHandlers
from bot.handlers_models import ModelHandlers
from bot.handlers_user import UserHandlers
from infra.logging.logger import get_logger, log_all_methods
from shared.bot_services import BotServices
from shared.config import BotTelegramConfig

# Константы для магических чисел
CONNECTION_POOL_SIZE = 20
POOL_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 20.0
CONNECT_TIMEOUT_SECONDS = 15.0
MONTHLY_QUOTA_DEFAULT = 100
FROG_THRESHOLD_DEFAULT = 70
TIMEOUT_SHORT_SECONDS = 5.0
TIMEOUT_MEDIUM_SECONDS = 30.0
TIMEOUT_BOT_INFO_SECONDS = 30.0


@log_all_methods()
class WednesdayBot:
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

    def __init__(self, services: BotServices, telegram_config: BotTelegramConfig) -> None:
        """Инициализирует WednesdayBot.

        Args:
            services: Контейнер сервисов бота (внедряется через DI).
            telegram_config: Конфигурация Telegram бота (внедряется через DI).

        Создает и настраивает все компоненты основного бота:
        - Application для работы с Telegram API
        - ImageGenerator для генерации изображений
        - UsageTracker для отслеживания лимитов генераций
        - ChatsStore для управления списком чатов
        - PromptCache, UserStateCache, RateLimiter для работы с Redis
        - UserHandlers, AdminHandlers, ModelHandlers для обработки команд

        Инициализирует все необходимые сервисы и готовит бота к запуску.
        """
        self.logger = get_logger(__name__)
        self.logger.info("Начало инициализации WednesdayBot")

        # Инициализируем компоненты
        self.logger.info("Создание HTTPXRequest с настройками подключения")
        request: HTTPXRequest = HTTPXRequest(
            connection_pool_size=CONNECTION_POOL_SIZE,
            pool_timeout=POOL_TIMEOUT_SECONDS,
            read_timeout=READ_TIMEOUT_SECONDS,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
        )
        # telegram_config.bot_token передается через DI
        telegram_token: str = telegram_config.bot_token or ""
        assert telegram_token, "TELEGRAM_BOT_TOKEN должен быть установлен"
        self.logger.info("Создание Application с токеном")
        self.application: Application = Application.builder().token(telegram_token).request(request).build()

        # Сервисы внедряются через конструктор (DI)
        self.services = services
        # bot_controller устанавливается в composition root (container.py) для избежания циклической зависимости
        # Данные для пост-старта (например, редактирование сообщения из SupportBot)
        self.pending_startup_edit: dict[str, Any] | None = None
        # Данные для пост-остановки (например, редактирование сообщения об остановке)
        self.pending_shutdown_edit: dict[str, Any] | None = None
        # Флаг, чтобы избежать дублирующих сообщений об остановке
        self._stop_message_sent: bool = False

        # Создаем обработчики команд
        self.logger.info("Создание специализированных наборов хендлеров")
        # Узкоспециализированные наборы для регистрации в PTB по зонам ответственности
        self.user_handlers: UserHandlers = UserHandlers(self.services)
        # Админские и пользовательские команды должны разделять общее состояние (лимиты, хранилища),
        # поэтому используем единый контейнер сервисов.
        self.admin_handlers: AdminHandlers = AdminHandlers(self.services)
        self.model_handlers: ModelHandlers = ModelHandlers(self.services)

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

        # Инициализация state coordinator для координации с SupportBot
        admin_chat_id_int = None
        if self.services.settings and self.services.settings.admin_chat_id:
            try:
                admin_chat_id_int = int(self.services.settings.admin_chat_id)
            except (ValueError, TypeError):
                pass
        self.state_coordinator = BotStateCoordinator(
            logger=self.logger,
            admin_chat_id=admin_chat_id_int,
        )

        # Флаг состояния бота
        self.is_running: bool = False
        # Event для ожидания сигнала остановки (вместо busy-wait цикла)
        self._stop_event = asyncio.Event()

        # Задача планировщика (инициализируется при старте)

        self.logger.info("WednesdayBot успешно инициализирован")

    def setup_handlers(self) -> None:
        """Настраивает обработчики команд для бота.

        Регистрирует все обработчики команд и событий в приложении:
        - Пользовательские команды: /start, /help, /frog, /status
        - Административные команды: /force_send, /log, /add_chat, /remove_chat,
          /list_chats, /stop, /set_kandinsky_model, /set_gigachat_model, /list_models,
          /mod, /unmod, /list_mods, /set_frog_limit, /set_frog_used
        - Обработчик неизвестных команд
        - Обработчик событий изменения статуса бота в чатах (on_my_chat_member)
        - Глобальный обработчик ошибок (_handle_error)

        Side Effects:
            - Регистрирует все обработчики команд через application.add_handler().
            - Регистрирует обработчик событий ChatMemberHandler.
            - Регистрирует глобальный обработчик ошибок через add_error_handler()
              (если метод доступен).
        """
        self.logger.info("Начало настройки обработчиков команд")

        # Регистрируем пользовательские команды
        self.application.add_handler(
            CommandHandler("start", self.user_handlers.start_command),
        )
        self.application.add_handler(
            CommandHandler("help", self.user_handlers.help_command),
        )
        self.application.add_handler(
            CommandHandler("frog", self.user_handlers.frog_command),
        )

        # Админские команды (регистрируем перед unknown_command!)
        self.application.add_handler(
            CommandHandler("status", self.admin_handlers.status_command),
        )
        self.application.add_handler(
            CommandHandler("force_send", self.admin_handlers.admin_force_send_command),
        )
        self.application.add_handler(
            CommandHandler("log", self.admin_handlers.admin_log_command),
        )
        self.application.add_handler(
            CommandHandler("add_chat", self.admin_handlers.admin_add_chat_command),
        )
        self.application.add_handler(
            CommandHandler("remove_chat", self.admin_handlers.admin_remove_chat_command),
        )
        self.application.add_handler(
            CommandHandler("stop", self.admin_handlers.stop_command),
        )
        self.application.add_handler(
            CommandHandler("list_chats", self.admin_handlers.list_chats_command),
        )
        self.application.add_handler(
            CommandHandler("mod", self.admin_handlers.mod_command),
        )
        self.application.add_handler(
            CommandHandler("unmod", self.admin_handlers.unmod_command),
        )
        self.application.add_handler(
            CommandHandler("list_mods", self.admin_handlers.list_mods_command),
        )
        # Админ: управление лимитами
        self.application.add_handler(
            CommandHandler("set_frog_limit", self.admin_handlers.set_frog_limit_command),
        )
        self.application.add_handler(
            CommandHandler("set_frog_used", self.admin_handlers.set_frog_used_command),
        )

        # Команды управления моделями
        self.application.add_handler(
            CommandHandler("set_kandinsky_model", self.model_handlers.set_kandinsky_model_command),
        )
        self.application.add_handler(
            CommandHandler("set_gigachat_model", self.model_handlers.set_gigachat_model_command),
        )
        self.application.add_handler(
            CommandHandler("list_models", self.model_handlers.list_models_command),
        )

        # Обработчик для неизвестных команд
        self.application.add_handler(
            MessageHandler(filters.COMMAND, self.user_handlers.unknown_command),
        )

        # Обработчик событий изменения статуса бота в чатах
        self.application.add_handler(
            ChatMemberHandler(
                self.chat_event_handler.on_my_chat_member,
                ChatMemberHandler.MY_CHAT_MEMBER,
            ),
        )

        self.logger.info("Обработчики команд успешно настроены и зарегистрированы")

        # Регистрируем глобальный обработчик ошибок, чтобы централизованно
        # отлавливать исключения из любых хендлеров и репортить их в Sentry.
        #
        # В проде объект Application всегда имеет метод add_error_handler,
        # но в юнит‑тестах может использоваться упрощённая заглушка без него.
        if hasattr(self.application, "add_error_handler"):
            self.application.add_error_handler(self.error_handler.handle_error)

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
        dispatch_service = self.services.dispatch_service
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
            - Настраивает обработчики команд через setup_handlers().
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
            self.setup_handlers()

            # Настраиваем и запускаем планировщик (только если используется старый планировщик)

            # Проверяем доступность чата перед отправкой сообщения
            if self.chat_id:
                await self.chat_validator.validate_chat_access(self.application.bot, self.chat_id)

            # Запускаем PTB Application через lifecycle manager
            await self.lifecycle_manager.start_application(self.application)

            # Отправляем уведомление о запуске
            if self.services.admin_notification_service:
                try:
                    startup_message = (
                        "🚀 Wednesday Frog Bot запущен!\n\n"
                        "✅ Бот активен и готов к работе\n"
                        "📅 Планировщик: включен (Celery)\n"
                        "🎨 Генератор изображений: Kandinsky API\n"
                        "📝 Логирование: включено\n\n"
                        "🐸 Используйте команду /frog для генерации жабы!"
                    )
                    chat_id_int = int(self.chat_id) if self.chat_id else None
                    admin_chat_id_str = (
                        str(self.services.settings.admin_chat_id)
                        if self.services.settings and self.services.settings.admin_chat_id
                        else None
                    )
                    await self.services.admin_notification_service.notify_lifecycle_event(
                        message=startup_message,
                        chat_id=chat_id_int,
                        admin_chat_id=admin_chat_id_str,
                        exclude_chat_id=chat_id_int,
                    )
                except Exception as send_error:
                    self.logger.warning(f"Не удалось отправить сообщение о запуске: {send_error}")
                    self.logger.info("Бот запущен, но не удалось отправить уведомление в чат")

            # Если был передан статус от SupportBot — дополняем его финальным состоянием основного
            if isinstance(self.pending_startup_edit, dict):
                state_data = BotStateData(
                    chat_id=self.pending_startup_edit.get("chat_id"),
                    message_id=self.pending_startup_edit.get("message_id"),
                )
                await self.state_coordinator.handle_startup_edit(
                    bot=self.application.bot,
                    state_data=state_data,
                )

            # Celery используется для планирования задач
            self.logger.info("Celery используется для планирования задач")

            # Устанавливаем флаг запуска и сбрасываем event для нового цикла
            self.is_running = True
            self._stop_event.clear()

            # Ожидаем сигнала остановки через Event (эффективнее, чем busy-wait цикл)
            # Event.wait() блокируется до вызова set() в методе stop()
            try:
                await self._stop_event.wait()
            except asyncio.CancelledError:
                self.logger.info("Получен сигнал отмены для основного цикла бота")
                self.is_running = False

        except Exception as e:
            self.logger.error(f"Ошибка при запуске бота: {e}")
            raise

    async def stop(self, shutdown_metadata: dict[str, Any] | None = None) -> None:
        """Останавливает бота и планировщик задач.

        Корректно завершает работу бота: останавливает планировщик, polling,
        отправляет уведомления об остановке и освобождает все ресурсы.
        Защищен от повторных вызовов через проверку is_running.

        Args:
            shutdown_metadata: Опциональные метаданные для редактирования статусного сообщения.
                Словарь с ключами 'chat_id' и 'message_id' или None.
                Если передан, используется вместо self.pending_shutdown_edit.

        Side Effects:
            - Устанавливает флаг is_running в False.
            - Останавливает PTB Application через lifecycle_manager.stop_application().
            - Отправляет сообщения об остановке в CHAT_ID и админам.
            - Редактирует статусные сообщения об остановке (если есть).
            - Гарантированно закрывает все ресурсы через services.cleanup() в finally блоке.
        """
        # Защита от повторных вызовов
        if not self.is_running:
            self.logger.info("Бот уже остановлен или остановка уже начата")
            return

        self.logger.info("Останавливаю Wednesday Bot")

        try:
            # Устанавливаем флаг остановки и разблокируем ожидание в start()
            self.is_running = False
            self._stop_event.set()  # Разблокирует await self._stop_event.wait() в start()

            # Останавливаем PTB Application через lifecycle manager
            await self.lifecycle_manager.stop_application(self.application)

            # Отправляем уведомление об остановке
            if self.services.admin_notification_service and not self._stop_message_sent:
                try:
                    shutdown_message = (
                        "🛑 Wednesday Frog Bot остановлен!\n\n📝 Логи сохранены в папке logs/\n👋 До свидания!"
                    )
                    chat_id_int = int(self.chat_id) if self.chat_id else None
                    admin_chat_id_str = (
                        str(self.services.settings.admin_chat_id)
                        if self.services.settings and self.services.settings.admin_chat_id
                        else None
                    )
                    await self.services.admin_notification_service.notify_lifecycle_event(
                        message=shutdown_message,
                        chat_id=chat_id_int,
                        admin_chat_id=admin_chat_id_str,
                        exclude_chat_id=chat_id_int,
                    )
                    self._stop_message_sent = True
                except Exception as send_error:
                    self.logger.debug(
                        f"Не удалось отправить сообщение об остановке (возможно, соединение уже закрыто): {send_error}",
                    )

            # Обновляем статусное сообщение от SupportBot
            # Используем переданные метаданные или внутреннее поле (для обратной совместимости)
            metadata = shutdown_metadata or self.pending_shutdown_edit
            if isinstance(metadata, dict):
                state_data = BotStateData(
                    chat_id=metadata.get("chat_id"),
                    message_id=metadata.get("message_id"),
                )
                await self.state_coordinator.handle_shutdown_edit(
                    bot=self.application.bot,
                    state_data=state_data,
                )

            # Очистим данные, чтобы не переиспользовать их при последующих переключениях
            self.pending_shutdown_edit = None
            self.pending_startup_edit = None

            self.logger.info("Бот успешно остановлен")

        except Exception as e:
            self.logger.error(f"Ошибка при остановке бота: {e}")
        finally:
            # Гарантированное закрытие ресурсов (всегда выполняется)
            try:
                await self.services.cleanup()
                self.logger.info("Все ресурсы BotServices закрыты")
            except Exception as cleanup_error:
                self.logger.warning(f"Ошибка при cleanup ресурсов: {cleanup_error}")

            # Дополнительно защитимся от повторных отправок в жизненном цикле объекта
            self._stop_message_sent = True

    async def get_bot_info(self) -> dict[str, Any]:
        """Получает информацию о боте.

        Возвращает основную информацию о боте: имя, username, ID и статус работы.
        Используется для мониторинга и проверки состояния бота.

        Returns:
            Словарь с информацией о боте:
            - name (str): Имя бота (first_name).
            - username (str | None): Username бота.
            - id (int): ID бота в Telegram.
            - is_running (bool): Статус работы бота.

            При ошибках возвращает словарь с ключами:
            - error (str): Тип ошибки (например, "Timeout").
            - error_message (str): Подробное описание ошибки.
            - is_running (bool): Текущий статус работы бота.

        Raises:
            TimeoutError: Если получение информации заняло больше TIMEOUT_MEDIUM_SECONDS секунд.
            Exception: При других ошибках (информация возвращается в виде словаря с error).
        """
        try:
            bot_info = await asyncio.wait_for(
                self.application.bot.get_me(),
                timeout=TIMEOUT_MEDIUM_SECONDS,
            )
            return {
                "name": bot_info.first_name,
                "username": bot_info.username,
                "id": bot_info.id,
                "is_running": self.is_running,
            }
        except TimeoutError:
            error_msg = (
                f"Таймаут при получении информации о боте ({TIMEOUT_BOT_INFO_SECONDS} секунд). "
                "Возможные причины: проблемы с интернет-соединением, недоступность Telegram API."
            )
            self.logger.error(error_msg)
            return {"error": "Timeout", "error_message": error_msg, "is_running": self.is_running}
        except Exception as e:
            error_type = type(e).__name__
            error_str = str(e)

            # Определяем тип ошибки для более информативного сообщения
            if "ConnectError" in error_type or "ConnectionError" in error_type or "Connection" in error_str:
                error_msg = (
                    f"Ошибка подключения к Telegram API при получении информации о боте.\n"
                    f"Тип: {error_type}\n"
                    f"Детали: {error_str[:200]}\n\n"
                    "Возможные причины:\n"
                    "- Проблемы с интернет-соединением\n"
                    "- Telegram API временно недоступен\n"
                    "- Проблемы с прокси (если используется)\n"
                    "- Блокировка доступа на стороне провайдера\n\n"
                    "Бот будет запущен, но некоторые функции могут быть недоступны."
                )
            else:
                error_msg = f"Ошибка при получении информации о боте: {error_type} - {error_str[:200]}"

            self.logger.error(f"Ошибка при получении информации о боте: {error_type} - {error_str}")
            return {"error": error_type, "error_message": error_msg, "is_running": self.is_running}
