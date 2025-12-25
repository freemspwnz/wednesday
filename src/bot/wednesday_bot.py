"""
Основной класс Wednesday Frog Bot.
Объединяет все компоненты бота и управляет его жизненным циклом.
"""

import asyncio
from typing import Any

from telegram import Update
from telegram.ext import Application, ChatMemberHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from bot.bot_chat_access_validator import BotChatAccessValidator
from bot.bot_error_handler import BotErrorHandler
from bot.bot_lifecycle_manager import BotLifecycleManager
from bot.bot_state_coordinator import BotStateCoordinator, BotStateData
from bot.handlers_admin import AdminHandlers
from bot.handlers_models import ModelHandlers
from bot.handlers_user import UserHandlers
from infra.logging.logger import get_logger, log_all_methods
from shared.bot_services import BotServices
from shared.config import Config

# Создаём экземпляр Config при импорте модуля
config: Config = Config()

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

    def __init__(self, services: BotServices) -> None:
        """Инициализирует WednesdayBot.

        Args:
            services: Контейнер сервисов бота (внедряется через DI).

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
        # config.telegram.bot_token проверяется при инициализации Config
        telegram_token: str = config.telegram.bot_token or ""
        assert telegram_token, "TELEGRAM_BOT_TOKEN должен быть установлен"
        self.logger.info("Создание Application с токеном")
        self.application: Application = Application.builder().token(telegram_token).request(request).build()

        # Сервисы внедряются через конструктор (DI)
        self.services = services
        # Устанавливаем обратную ссылку для команд управления
        self.services.bot_controller = self

        # Создаём messaging_service и обновляем dispatch сервисы
        from infra.container import build_dispatch_services
        from infra.messaging.ptb import PTBMessagingService

        messaging_service = PTBMessagingService(bot=self.application.bot)
        self.services.messaging_service = messaging_service

        # Обновляем dispatch сервисы с messaging_service
        if self.services.database_operations is not None and self.services.admins_repo is not None:
            _target_prep, _dispatch_delivery, dispatch, admin_notifier = build_dispatch_services(
                messaging_service=messaging_service,
                chats=self.services.chats,
                dispatch_registry=self.services.dispatch_registry,
                database_operations=self.services.database_operations,
                image_service=self.services.image_service,
                metrics=self.services.metrics,
                admins_repo=self.services.admins_repo,
                logger=self.logger,
            )
            # Обновляем services
            self.services.dispatch_service = dispatch
            self.services.admin_notification_service = admin_notifier
        else:
            self.logger.warning("database_operations или admins_repo не доступны, dispatch_service не будет создан")
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
        self.chat_id: str | None = config.telegram.chat_id
        self.logger.info(f"Chat ID установлен: {self.chat_id}")

        # Инициализация компонентов для управления жизненным циклом
        self.error_handler = BotErrorHandler(self.logger)
        self.chat_validator = BotChatAccessValidator(self.logger, timeout=TIMEOUT_MEDIUM_SECONDS)
        self.lifecycle_manager = BotLifecycleManager(self.logger)

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
            ChatMemberHandler(self.on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER),
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

        Генерирует изображение жабы и отправляет его во все настроенные чаты.
        Использует dispatch registry для предотвращения дублирования отправок
        в один и тот же тайм-слот. При ошибках генерации использует fallback
        из случайных сохраненных изображений.

        Args:
            slot_time: Опциональное время слота в формате "HH:MM" для идентификации
                отправки. Если None, определяется автоматически на основе текущего
                времени и настроенных времен отправки.

        Side Effects:
            - Вызывает image_generator.generate_frog_image() для генерации изображения.
            - Сохраняет изображение локально через image_generator.save_image_locally().
            - Отправляет изображение во все активные чаты через bot.send_image().
            - Использует dispatch_registry для отслеживания отправленных слотов.
            - Вызывает usage.increment() для увеличения счетчика использования.
            - Вызывает metrics.increment_dispatch_success/failed() для метрик.
            - При ошибках отправляет fallback изображения и уведомления администраторам.
        """
        from datetime import datetime

        now = datetime.now()
        slot_date = now.strftime("%Y-%m-%d")
        # Если слот не передан планировщиком — сопоставим ближайший (<= now)
        if slot_time is None:
            # Используем конфигурацию из настроек приложения, а не внутреннее состояние планировщика
            try:
                configured_times: list[str] = list(self.services.settings.scheduler_send_times or [])
            except Exception:
                configured_times = []
            resolved_slot: str | None = None
            if configured_times:
                try:
                    candidates: list[tuple[datetime, str]] = []
                    for t in configured_times:
                        time_format_length = self.services.settings.time_format_length

                        if len(t) == time_format_length and t[2] == ":" and t[:2].isdigit() and t[3:].isdigit():
                            h, m = int(t[:2]), int(t[3:])
                            candidate_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                            if candidate_dt <= now:
                                candidates.append((candidate_dt, t))
                    if candidates:
                        candidates.sort(key=lambda x: x[0])
                        resolved_slot = candidates[-1][1]
                except Exception:
                    resolved_slot = None
            slot_time = resolved_slot or now.strftime("%H:%M")

        self.logger.info("Выполняю запланированную отправку жабы")

        dispatch_service = self.services.dispatch_service
        if dispatch_service is None:
            self.logger.error("DispatchService недоступен, пропускаю рассылку")
            return

        await dispatch_service.send_wednesday_frog(
            slot_date=slot_date,
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
            - Проверяет доступность чата через _check_chat_access().
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
        # День недели и таймзона берутся из глобальной конфигурации, но не протекают через протокол планировщика
        from shared.config import Config

        # Используем глобальный config из модуля
        if isinstance(config, Config):
            wednesday_day = config.scheduler.wednesday_day
            timezone = config.scheduler.tz or "Europe/Moscow"
        else:
            wednesday_day = config.scheduler_wednesday_day
            timezone = config.scheduler_tz or "Europe/Moscow"

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

    async def on_my_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик событий изменения статуса бота в чатах.

        Обрабатывает события, когда бот добавляется или удаляется из чата.
        Автоматически добавляет чат в список рассылки при добавлении бота и
        удаляет при удалении бота из чата.

        Args:
            update: Объект обновления Telegram, содержащий информацию о событии
                изменения статуса бота в чате через update.my_chat_member.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков событий).

        Side Effects:
            - При добавлении бота: вызывает chats.add_chat() для добавления чата
              и отправляет приветственное сообщение.
            - При удалении бота: вызывает chats.remove_chat() для удаления чата
              из списка рассылки.
            - Логирует все операции и ошибки.
        """
        try:
            my_cm = update.my_chat_member
            if not my_cm:
                return
            old = getattr(my_cm.old_chat_member, "status", None)
            new = getattr(my_cm.new_chat_member, "status", None)
            chat = my_cm.chat
            chat_id = chat.id
            title = getattr(chat, "title", None) or getattr(chat, "username", "") or ""

            # Бот добавлен/активирован в чате
            if new in {"member", "administrator"} and old in {"left", "kicked", "restricted", None}:
                await self.services.chats.add_chat(chat_id, title)
                welcome = (
                    "🐸 Привет! Я Wednesday Frog Bot.\n\n"
                    "Я присылаю картинки с жабой по средам (09:00, 12:00, 18:00 по Мск), "
                    "а также по команде /frog (если не превышен лимит ручных генераций).\n\n"
                    "Доступные команды:\n"
                    "• /start — информация\n"
                    "• /help — справка\n"
                    "• /frog — сгенерировать жабу сейчас\n"
                )
                try:
                    await self.application.bot.send_message(chat_id=chat_id, text=welcome)
                except Exception as e:
                    self.logger.warning(f"Не удалось отправить приветствие в чат {chat_id}: {e}")

            # Бот удалён из чата
            if new in {"left", "kicked"} and old in {"member", "administrator", "restricted"}:
                await self.services.chats.remove_chat(chat_id)

        except Exception as e:
            self.logger.error(f"Ошибка в on_my_chat_member: {e}")

    async def _check_chat_access(self) -> None:
        """Проверяет доступность чата для отправки сообщений.

        Выполняет проверку доступа к чату, указанному в self.chat_id, перед запуском.
        Использует увеличенный таймаут для более надежной проверки. Предупреждения
        логируются, но не блокируют запуск бота.

        Side Effects:
            - Вызывает bot.get_chat() для получения информации о чате.
            - Логирует результат проверки или предупреждения при ошибках.
            - Не блокирует запуск бота при ошибках, только предупреждает.

        Raises:
            TimeoutError: Если проверка заняла больше TIMEOUT_MEDIUM_SECONDS секунд.
            Exception: При других ошибках доступа к чату (логируется, но не пробрасывается).
        """
        try:
            # Пытаемся получить информацию о чате с увеличенным таймаутом
            chat_info = await asyncio.wait_for(
                self.application.bot.get_chat(self.chat_id),
                timeout=TIMEOUT_MEDIUM_SECONDS,
            )
            self.logger.info(f"Чат доступен: {chat_info.title or chat_info.first_name}")
        except TimeoutError:
            self.logger.warning(f"Таймаут при проверке доступа к чату {self.chat_id}")
            self.logger.warning("Возможно, проблемы с сетью или Telegram API")
            self.logger.warning("Бот будет работать, но проверка доступа к чату не выполнена")
        except Exception as e:
            self.logger.warning(f"Не удалось получить доступ к чату {self.chat_id}: {e}")
            self.logger.warning("Бот будет работать, но не сможет отправлять сообщения в указанный чат")
            self.logger.warning("Убедитесь, что:")
            self.logger.warning("1. CHAT_ID указан правильно")
            self.logger.warning("2. Бот добавлен в чат/канал")
            self.logger.warning("3. У бота есть права на отправку сообщений")

    async def stop(self) -> None:
        """Останавливает бота и планировщик задач.

        Корректно завершает работу бота: останавливает планировщик, polling,
        отправляет уведомления об остановке и освобождает все ресурсы.
        Защищен от повторных вызовов через проверку is_running.

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
            if isinstance(self.pending_shutdown_edit, dict):
                state_data = BotStateData(
                    chat_id=self.pending_shutdown_edit.get("chat_id"),
                    message_id=self.pending_shutdown_edit.get("message_id"),
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
