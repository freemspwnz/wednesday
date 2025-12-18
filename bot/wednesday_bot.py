"""
Основной класс Wednesday Frog Bot.
Объединяет все компоненты бота и управляет его жизненным циклом.
"""

import asyncio
import os
from typing import Any

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, ChatMemberHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from bot.handlers_admin import AdminHandlers
from bot.handlers_models import ModelHandlers
from bot.handlers_user import UserHandlers
from services.bot_services import BotServices
from services.clients import get_image_client_container, get_text_client_container
from services.container import build_bot_services
from utils.config import config
from utils.logger import get_logger, log_all_methods, log_event

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
MAX_POLLING_ATTEMPTS = 3  # максимальное количество попыток запуска polling
LAST_POLLING_ATTEMPT_INDEX = 2  # индекс последней попытки (0-based: 2 = 3-я попытка)


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
    - Использует планировщик задач (TaskScheduler или Celery) для автоматических отправок

    Бот управляет жизненным циклом всех компонентов: от инициализации до
    корректной остановки с освобождением ресурсов.
    """

    def __init__(self) -> None:
        """Инициализирует WednesdayBot.

        Создает и настраивает все компоненты основного бота:
        - Application для работы с Telegram API
        - ImageGenerator для генерации изображений
        - TaskScheduler (опционально) для планирования задач
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
        # config.telegram_token проверяется в _validate_required_vars, поэтому не может быть None
        telegram_token: str = config.telegram_token or ""
        assert telegram_token, "TELEGRAM_BOT_TOKEN должен быть установлен"
        self.logger.info("Создание Application с токеном")
        self.application: Application = Application.builder().token(telegram_token).request(request).build()

        # Создаем сервисы через DI‑контейнер
        self.logger.info("Инициализация сервисов через DI‑контейнер BotServices")
        self.services: BotServices = build_bot_services()
        # Устанавливаем ссылку на экземпляр бота для команд управления
        self.services.bot_controller = self
        # Данные для пост-старта (например, редактирование сообщения из SupportBot)
        self.pending_startup_edit: dict[str, Any] | None = None
        # Данные для пост-остановки (например, редактирование сообщения об остановке)
        self.pending_shutdown_edit: dict[str, Any] | None = None
        # Флаг, чтобы избежать дублирующих сообщений об остановке
        self._stop_message_sent: bool = False

        # Создаем обработчики команд
        self.logger.info("Создание специализированных наборов хендлеров")
        # Для get_next_run используем scheduler если он есть, иначе None (Celery управляет расписанием)
        get_next_run_fn = self.services.scheduler.get_next_run if self.services.scheduler else lambda: None
        # Узкоспециализированные наборы для регистрации в PTB по зонам ответственности
        self.user_handlers: UserHandlers = UserHandlers(self.services, get_next_run_fn)
        # Админские и пользовательские команды должны разделять общее состояние (лимиты, хранилища),
        # поэтому используем единый контейнер сервисов и один и тот же next_run_provider.
        self.admin_handlers: AdminHandlers = AdminHandlers(self.services, get_next_run_fn)
        self.model_handlers: ModelHandlers = ModelHandlers(self.services, get_next_run_fn)

        # ID чата для отправки сообщений
        self.chat_id: str | None = config.chat_id
        self.logger.info(f"Chat ID установлен: {self.chat_id}")

        # Флаг состояния бота
        self.is_running: bool = False

        # Задача планировщика (инициализируется при старте)
        self.scheduler_task: asyncio.Task[None] | None = None

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
            self.application.add_error_handler(self._handle_error)

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
            - Отправляет изображение во все активные чаты через bot.send_photo().
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
            send_error_message=self._send_error_message,
            send_admin_error=self._send_admin_error,
            send_user_friendly_error=self._send_user_friendly_error,
            send_fallback_image=self._send_fallback_image,
            send_photo=self.application.bot.send_photo,
        )

    async def _send_error_message(self, error_text: str) -> None:
        """Отправляет сообщение об ошибке в основной чат.

        Вспомогательная функция для отправки дружелюбного сообщения об ошибке
        в чат, указанный в self.chat_id.

        Args:
            error_text: Текст сообщения об ошибке, который будет дополнен
                стандартным префиксом и эмодзи.

        Side Effects:
            - Отправляет сообщение в чат через bot.send_message().
            - Логирует ошибку, если отправка не удалась.
        """
        try:
            error_message = f"⚠️ {error_text}\nПопробуем в следующий раз! 🐸"
            await self.application.bot.send_message(
                chat_id=self.chat_id,
                text=error_message,
            )
        except TelegramError as send_error:
            self.logger.warning(f"Не удалось отправить сообщение об ошибке (TelegramError): {send_error}")
        except Exception as send_error:
            self.logger.error(
                f"Неожиданная программная ошибка при отправке сообщения об ошибке: {send_error}",
                exc_info=True,
            )

    async def _send_user_friendly_error(self, chat_id: int, error_context: str = "генерации изображения") -> None:
        """Отправляет дружелюбное сообщение об ошибке в указанный чат.

        Вспомогательная функция для отправки пользователю дружелюбного сообщения
        об ошибке, которое не раскрывает технических деталей.

        Args:
            chat_id: ID чата для отправки сообщения.
            error_context: Контекст ошибки для пользовательского сообщения
                (по умолчанию "генерации изображения").

        Side Effects:
            - Отправляет дружелюбное сообщение в указанный чат через bot.send_message().
            - Логирует ошибку, если отправка не удалась.
        """
        try:
            friendly_message = (
                "🐸 К сожалению, не удалось сгенерировать новую картинку.\n"
                "Но не расстраивайтесь! Вот случайная картинка из архива! 🎲"
            )
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=friendly_message,
            )
        except TelegramError as send_error:
            self.logger.warning(
                "Не удалось отправить дружелюбное сообщение об ошибке (TelegramError): %s",
                send_error,
            )
        except Exception as send_error:
            self.logger.error(
                "Неожиданная программная ошибка при отправке дружелюбного сообщения об ошибке: %s",
                send_error,
                exc_info=True,
            )

    async def _send_admin_error(self, error_details: str) -> None:
        """Отправляет детальное сообщение об ошибке всем администраторам.

        Вспомогательная функция для отправки технического сообщения об ошибке
        всем администраторам бота. Сообщения автоматически обрезаются, если
        превышают лимит Telegram (4096 символов).

        Args:
            error_details: Детальная техническая информация об ошибке,
                включающая типы ошибок, трейсы и возможные причины.

        Side Effects:
            - Получает список всех администраторов через AdminsStore.
            - Отправляет детальное сообщение каждому администратору через bot.send_message().
            - Автоматически обрезает длинные сообщения до безопасного размера.
            - Логирует ошибки при отправке.
        """
        from utils.admins_store import AdminsStore

        admins_store = AdminsStore()
        all_admins = await admins_store.list_all_admins()

        if not all_admins:
            self.logger.warning("Нет администраторов для отправки ошибки")
            return

        admin_message = f"⚠️ Ошибка генерации изображения:\n\n{error_details}"

        # Разбиваем длинные сообщения на части (лимит Telegram: 4096 символов)
        max_message_length = 4000  # Оставляем запас

        for admin_id in all_admins:
            try:
                if len(admin_message) > max_message_length:
                    # Отправляем короткую версию
                    short_message = error_details[:3000] + "\n\n⚠️ Сообщение обрезано, полный текст в логах."
                    await self.application.bot.send_message(
                        chat_id=admin_id,
                        text=short_message,
                    )
                else:
                    await self.application.bot.send_message(
                        chat_id=admin_id,
                        text=admin_message,
                    )
                self.logger.info(f"Отправлено сообщение об ошибке админу {admin_id}")
            except TelegramError as send_error:
                error_str = str(send_error)
                # Если ошибка "Message is too long", отправляем сокращенную версию
                if "too long" in error_str.lower():
                    try:
                        short_message = error_details[:2000] + "\n\n⚠️ Полное сообщение слишком длинное, смотрите логи."
                        await self.application.bot.send_message(
                            chat_id=admin_id,
                            text=short_message,
                        )
                        self.logger.info(f"Отправлено сокращенное сообщение об ошибке админу {admin_id}")
                    except TelegramError as retry_error:
                        self.logger.error(
                            "Не удалось отправить даже сокращенное сообщение админу %s (TelegramError): %s",
                            admin_id,
                            retry_error,
                        )
                    except Exception as retry_error:
                        self.logger.error(
                            "Неожиданная ошибка при отправке сокращённого сообщения админу %s: %s",
                            admin_id,
                            retry_error,
                            exc_info=True,
                        )
                else:
                    self.logger.error(
                        "Не удалось отправить сообщение об ошибке админу %s (TelegramError): %s",
                        admin_id,
                        send_error,
                    )
            except Exception as send_error:
                self.logger.error(
                    "Неожиданная программная ошибка при отправке сообщения об ошибке админу %s: %s",
                    admin_id,
                    send_error,
                    exc_info=True,
                )

    async def _send_fallback_image(self, chat_id: int) -> bool:
        """Отправляет случайное изображение из сохраненных в случае ошибки генерации.

        Вспомогательная функция для отправки случайного изображения из архива
        когда не удалось сгенерировать новое изображение.

        Args:
            chat_id: ID чата для отправки изображения.

        Returns:
            True если изображение успешно отправлено, False если нет сохраненных
            изображений или произошла ошибка при отправке.

        Side Effects:
            - Получает случайное изображение через image_generator.get_random_saved_image().
            - Отправляет изображение в указанный чат через bot.send_photo().
            - Логирует результат операции.
        """
        try:
            # Чтение fallback‑изображения выполняется через публичный метод ImageService,
            # который инкапсулирует детали инфраструктурного хранилища.
            image_service = self.services.image_service
            if image_service is None:
                self.logger.warning("Сервис изображений недоступен для fallback-изображения")
                return False

            fallback_image = await image_service.get_random_saved_image()
            if fallback_image:
                image_data, caption = fallback_image
                await self.application.bot.send_photo(
                    chat_id=chat_id,
                    photo=image_data,
                    caption=caption,
                )
                self.logger.info(f"Случайное изображение отправлено в чат {chat_id} как fallback")
                return True
            else:
                self.logger.warning("Нет сохраненных изображений для отправки как fallback")
                return False
        except TelegramError as send_error:
            self.logger.warning(
                "Не удалось отправить fallback-изображение в чат %s (TelegramError): %s",
                chat_id,
                send_error,
            )
            return False
        except Exception as e:
            self.logger.error(
                "Неожиданная программная ошибка при отправке fallback-изображения в чат %s: %s",
                chat_id,
                e,
                exc_info=True,
            )
            return False

    def setup_scheduler(self) -> None:
        """Настраивает планировщик задач для автоматической отправки жабы.

        Настраивает TaskScheduler для автоматической отправки изображений жабы
        по расписанию. Используется только если USE_OLD_SCHEDULER=true.
        Иначе используется Celery (запускается отдельно через celery worker/beat).

        Side Effects:
            - Планирует задачу отправки жабы каждую среду через scheduler.schedule_wednesday_task().
            - Опционально планирует тестовый интервал через scheduler.schedule_interval_task(),
              если установлена переменная окружения SCHEDULER_TEST_MINUTES.

        Note:
            Если TaskScheduler отключен (self.services.scheduler is None), метод ничего не делает,
            так как планирование выполняется через Celery.
        """
        if not self.services.scheduler:
            self.logger.info("TaskScheduler отключен, используется Celery для планирования задач")
            return

        self.logger.info("Настраиваю планировщик задач (старый TaskScheduler)")

        # Планируем отправку жабы каждую среду
        self.services.scheduler.schedule_wednesday_task(self.send_wednesday_frog)

        # Необязательный тестовый интервал для проверки планировщика
        test_minutes = os.getenv("SCHEDULER_TEST_MINUTES")
        if test_minutes:
            try:
                minutes = int(test_minutes)
                if minutes > 0:
                    self.logger.info(f"Включен тестовый интервал планировщика: каждые {minutes} минут")
                    self.services.scheduler.schedule_interval_task(self.send_wednesday_frog, minutes)
            except ValueError:
                self.logger.warning("Переменная SCHEDULER_TEST_MINUTES должна быть целым числом")

        self.logger.info("Планировщик задач настроен")

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
            - Настраивает планировщик через setup_scheduler() (если включен).
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
        from utils.config import config as _config

        wednesday_day = _config.scheduler_wednesday_day
        timezone = _config.scheduler_tz or "Europe/Moscow"

        if self.services.scheduler:
            self.logger.info(
                "Валидация планировщика (TaskScheduler): "
                f"день недели={wednesday_day}, времена={configured_times}, TZ={timezone}",
            )
        else:
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
            self.setup_scheduler()

            # Проверяем доступность чата перед отправкой сообщения
            await self._check_chat_access()

            # Инициализируем приложение асинхронно
            await self.application.initialize()

            # Все зависимости доступны через BotServices, bot_data больше не используется для DI

            # Ретраи запуска сети (start + polling)
            delay = 3
            for attempt in range(3):
                try:
                    await self.application.start()
                    updater = self.application.updater
                    if updater:
                        await updater.start_polling(
                            allowed_updates=Update.ALL_TYPES,
                            drop_pending_updates=True,
                        )
                    break
                except Exception as e:
                    self.logger.warning(
                        f"Не удалось запустить polling (попытка {attempt + 1}/{MAX_POLLING_ATTEMPTS}): {e}",
                    )
                    if attempt == LAST_POLLING_ATTEMPT_INDEX:
                        raise
                    await asyncio.sleep(delay)
                    delay *= 2

            # Отправляем сообщение о запуске после старта
            try:
                scheduler_status = "включен (Celery)" if not self.services.scheduler else "включен (TaskScheduler)"
                startup_message = (
                    "🚀 Wednesday Frog Bot запущен!\n\n"
                    "✅ Бот активен и готов к работе\n"
                    f"📅 Планировщик: {scheduler_status}\n"
                    "🎨 Генератор изображений: Kandinsky API\n"
                    "📝 Логирование: включено\n\n"
                    "🐸 Используйте команду /frog для генерации жабы!"
                )
                await self.application.bot.send_message(
                    chat_id=self.chat_id,
                    text=startup_message,
                )
                # Дублируем в админ-чат, если задан, избегая повтора, если CHAT_ID совпадает
                try:
                    from utils.admins_store import AdminsStore as _AdminsStore
                    from utils.config import config as _cfg

                    admin_chat_id_env = getattr(_cfg, "admin_chat_id", None)
                    if admin_chat_id_env:
                        try:
                            admin_chat_id_val = int(str(admin_chat_id_env))
                            chat_id_val = int(str(self.chat_id)) if self.chat_id is not None else None
                            if chat_id_val != admin_chat_id_val:
                                await self.application.bot.send_message(
                                    chat_id=admin_chat_id_val,
                                    text=startup_message,
                                )
                        except Exception:
                            pass
                    else:
                        # Если ADMIN_CHAT_ID не задан, разошлем всем админам из хранилища (без дубля с CHAT_ID)
                        try:
                            admins = await _AdminsStore().list_all_admins()
                            for admin_id in admins:
                                try:
                                    chat_id_val = int(str(self.chat_id)) if self.chat_id is not None else None
                                    if chat_id_val is not None and admin_id == chat_id_val:
                                        continue
                                    await self.application.bot.send_message(
                                        chat_id=admin_id,
                                        text=startup_message,
                                    )
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception:
                    pass
                self.logger.info("Сообщение о запуске отправлено")
            except Exception as send_error:
                self.logger.warning(f"Не удалось отправить сообщение о запуске: {send_error}")
                self.logger.info("Бот запущен, но не удалось отправить уведомление в чат")

            # Если был передан статус от SupportBot — дополняем его финальным состоянием основного
            try:
                if isinstance(self.pending_startup_edit, dict):
                    chat_id = self.pending_startup_edit.get("chat_id")
                    message_id = self.pending_startup_edit.get("message_id")
                    # Не редактируем сообщение в админском чате — оно предназначено для других чатов
                    skip_admin_edit = False
                    try:
                        from utils.config import config as _cfg

                        admin_chat_id_env = getattr(_cfg, "admin_chat_id", None)
                        if admin_chat_id_env:
                            try:
                                admin_chat_str: str = str(admin_chat_id_env)
                                chat_id_str: str = str(chat_id) if chat_id is not None else ""
                                if admin_chat_str and chat_id_str:
                                    skip_admin_edit = int(admin_chat_str) == int(chat_id_str)
                                else:
                                    skip_admin_edit = False
                            except Exception:
                                skip_admin_edit = False
                    except Exception:
                        skip_admin_edit = False

                    if chat_id and message_id and not skip_admin_edit:
                        # Финальный текст после фактической остановки Support Bot и запуска основного
                        final_text = "🛑 Support Bot остановлен\n✅ Wednesday Frog Bot запущен"
                        await self.application.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=final_text,
                        )
                        self.logger.info("Основной бот подтвердил запуск в сообщение SupportBot")
                    elif chat_id and skip_admin_edit:
                        self.logger.info("Пропускаю редактирование статусного сообщения в админском чате")
            except Exception as e:
                self.logger.warning(f"Не удалось обновить статусное сообщение SupportBot: {e}")

            # Запускаем планировщик в фоновой задаче (только если используется старый планировщик)
            if self.services.scheduler:
                self.scheduler_task = asyncio.create_task(self.services.scheduler.start())
            else:
                self.scheduler_task = None
                self.logger.info("Celery используется для планирования, TaskScheduler не запущен")

            # Устанавливаем флаг запуска
            self.is_running = True

            # Бесконечный цикл для поддержания работы бота
            # Он будет работать до получения сигнала остановки
            while self.is_running:
                try:
                    # Используем await asyncio.sleep вместо обычного sleep
                    # Это позволяет корректно обрабатывать прерывания
                    await asyncio.sleep(0.1)
                except asyncio.CancelledError:
                    self.logger.info("Получен сигнал отмены для основного цикла бота")
                    self.is_running = False
                    break

        except Exception as e:
            self.logger.error(f"Ошибка при запуске бота: {e}")
            raise

    async def _handle_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Глобальный обработчик ошибок PTB.

        Централизованный обработчик всех необработанных исключений из обработчиков
        команд и сообщений. Обеспечивает логирование, отправку в Sentry (если включен)
        и структурированное логирование для дальнейшего анализа.

        Args:
            update: Объект обновления Telegram, которое вызвало ошибку
                (может быть любого типа в зависимости от события).
            context: Контекст бота, содержащий информацию об ошибке через
                context.error и другие метаданные.

        Side Effects:
            - Логирует ошибку с полным стеком через logger.error().
            - Отправляет исключение в Sentry через sentry_sdk.capture_exception()
              (если SDK инициализирован).
            - Записывает структурированное событие через log_event() для анализа.
        """
        error = getattr(context, "error", None)
        self.logger.error(f"Необработанное исключение в обработчике PTB: {error!r}", exc_info=True)

        # Отправляем исключение в Sentry, если SDK инициализирован.
        if error is not None:
            try:
                import sentry_sdk

                sentry_sdk.capture_exception(error)
            except Exception:
                # Ошибки в интеграции Sentry не должны ломать основной поток.
                pass

        # Логируем структурированное событие для унифицированного JSON‑логирования.
        try:
            log_event(
                event="unhandled_exception",
                status="error",
                extra={
                    "where": "ptb_error_handler",
                    "error": repr(error),
                    "update_repr": repr(update),
                },
                level="error",
                message="Необработанное исключение в обработчике PTB",
            )
        except Exception:
            # Любые ошибки логирования здесь игнорируем, чтобы не усугублять ситуацию.
            pass

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
            - Останавливает планировщик через scheduler.stop() (если включен).
            - Отменяет задачу планировщика (scheduler_task.cancel()).
            - Останавливает updater через updater.stop().
            - Отправляет сообщения об остановке в CHAT_ID и админам.
            - Редактирует статусные сообщения об остановке (если есть).
            - Останавливает приложение через application.stop().
        """
        # Защита от повторных вызовов
        if not self.is_running:
            self.logger.info("Бот уже остановлен или остановка уже начата")
            return

        self.logger.info("Останавливаю Wednesday Bot")

        try:
            # Устанавливаем флаг остановки
            self.is_running = False

            # Останавливаем планировщик (только если используется старый планировщик)
            try:
                if self.services.scheduler and hasattr(self, "scheduler_task") and self.scheduler_task:
                    self.services.scheduler.stop()
                    self.scheduler_task.cancel()
                    try:
                        await self.scheduler_task
                    except asyncio.CancelledError:
                        pass
            except Exception as e:
                self.logger.warning(f"Ошибка при остановке планировщика: {e}")

            # Безопасная остановка updater'а
            try:
                if hasattr(self.application, "updater") and self.application.updater:
                    await self.application.updater.stop()
            except Exception as e:
                self.logger.warning(f"Ошибка при остановке updater'а: {e}")
            # Небольшая пауза, чтобы освободить соединения пула перед отправкой финальных сообщений
            try:
                await asyncio.sleep(0.2)
            except Exception:
                pass

            # Отправляем сообщение об остановке в CHAT_ID после остановки polling (во избежание Pool timeout)
            try:
                if self.application and self.application.bot and hasattr(self.application.bot, "send_message"):
                    has_pending_edit = hasattr(self, "pending_shutdown_edit") and isinstance(
                        self.pending_shutdown_edit,
                        dict,
                    )
                    if (not has_pending_edit) and (not self._stop_message_sent):
                        shutdown_message = (
                            "🛑 Wednesday Frog Bot остановлен!\n\n📝 Логи сохранены в папке logs/\n👋 До свидания!"
                        )
                        await asyncio.wait_for(
                            self.application.bot.send_message(
                                chat_id=self.chat_id,
                                text=shutdown_message,
                            ),
                            timeout=TIMEOUT_SHORT_SECONDS,
                        )
                        self.logger.info("Сообщение об остановке отправлено")
                        self._stop_message_sent = True
            except TimeoutError:
                self.logger.warning("Таймаут при отправке сообщения об остановке")
            except Exception as send_error:
                self.logger.debug(
                    f"Не удалось отправить сообщение об остановке (возможно, соединение уже закрыто): {send_error}",
                )

            # Обновляем статусное сообщение в чате-источнике: основной бот остановлен (кроме админ-чата)
            try:
                if hasattr(self, "pending_shutdown_edit") and isinstance(self.pending_shutdown_edit, dict):
                    chat_id = self.pending_shutdown_edit.get("chat_id")
                    message_id = self.pending_shutdown_edit.get("message_id")
                    # Не редактируем в админском чате
                    skip_admin_edit = False
                    try:
                        from utils.config import config as _cfg

                        admin_chat_id_env = getattr(_cfg, "admin_chat_id", None)
                        if admin_chat_id_env:
                            try:
                                admin_chat_str: str = str(admin_chat_id_env)
                                chat_id_str: str = str(chat_id) if chat_id is not None else ""
                                if admin_chat_str and chat_id_str:
                                    skip_admin_edit = int(admin_chat_str) == int(chat_id_str)
                                else:
                                    skip_admin_edit = False
                            except Exception:
                                skip_admin_edit = False
                    except Exception:
                        skip_admin_edit = False

                    if chat_id and message_id and not skip_admin_edit:
                        await self.application.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=("🛑 Wednesday Frog Bot остановлен!"),
                        )
                        self.logger.info("Статусное сообщение обновлено: основной бот остановлен")
                    elif chat_id and skip_admin_edit:
                        self.logger.info(
                            "Пропускаю редактирование статусного сообщения в админском чате (остановка основного)",
                        )
            except Exception as e:
                self.logger.warning(f"Не удалось обновить статусное сообщение об остановке: {e}")
            finally:
                # Очистим данные, чтобы не переиспользовать их при последующих переключениях
                self.pending_shutdown_edit = None
                self.pending_startup_edit = None

            # Безопасная остановка приложения
            try:
                await self.application.stop()
            except Exception as e:
                self.logger.warning(f"Ошибка при остановке приложения: {e}")

            # Финальный шаг жизненного цикла PTB: корректный shutdown приложения
            try:
                await self.application.shutdown()
            except Exception as e:
                self.logger.warning(f"Ошибка при shutdown приложения: {e}")

            # Закрываем ML-клиенты (контейнеры управляют HTTP-сессиями внутри)
            await self.aclose()

            self.logger.info("Бот успешно остановлен")

        except Exception as e:
            self.logger.error(f"Ошибка при остановке бота: {e}")
        finally:
            # Рассылка длинного сообщения об остановке также в админ-чат(ы), избегая дубля с CHAT_ID
            try:
                shutdown_message = (
                    "🛑 Wednesday Frog Bot остановлен!\n\n📝 Логи сохранены в папке logs/\n👋 До свидания!"
                )
                from utils.admins_store import AdminsStore
                from utils.config import config as _cfg

                admin_chat_id_env = getattr(_cfg, "admin_chat_id", None)
                has_pending_edit = hasattr(self, "pending_shutdown_edit") and isinstance(
                    self.pending_shutdown_edit,
                    dict,
                )
                if admin_chat_id_env and (not self._stop_message_sent):
                    try:
                        admin_chat_id_val = int(str(admin_chat_id_env))
                        chat_id_val = int(str(self.chat_id)) if self.chat_id is not None else None
                        # Если админ-чат совпадает с CHAT_ID и сообщение уже отправлено в try — пропускаем
                        if chat_id_val == admin_chat_id_val and self._stop_message_sent:
                            # Сообщение уже отправлено в CHAT_ID, пропускаем дубль
                            pass
                        elif has_pending_edit or (chat_id_val != admin_chat_id_val):
                            await self.application.bot.send_message(
                                chat_id=admin_chat_id_val,
                                text=shutdown_message,
                            )
                            self._stop_message_sent = True
                    except Exception:
                        pass
                else:
                    admins = await AdminsStore().list_all_admins()
                    for admin_id in admins:
                        try:
                            chat_id_val = int(str(self.chat_id)) if self.chat_id is not None else None
                            # Если был pending edit — не пропускаем даже если это тот же чат;
                            # иначе избегаем дубля с CHAT_ID
                            if not has_pending_edit:
                                if chat_id_val is not None and admin_id == chat_id_val:
                                    continue
                            await self.application.bot.send_message(
                                chat_id=admin_id,
                                text=shutdown_message,
                            )
                            self._stop_message_sent = True
                        except Exception:
                            pass
            except Exception:
                pass
            finally:
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

    async def aclose(self) -> None:
        """Закрывает async ресурсы бота (ML-клиенты).

        Закрывает контейнеры ML-клиентов (ImageClientContainer, TextClientContainer),
        что гарантирует корректное закрытие всех HTTP-сессий (aiohttp).

        Этот метод должен вызываться при остановке standalone-бота для гарантированного
        освобождения всех ресурсов. В Celery worker контейнеры закрываются автоматически
        через shutdown_services() при остановке worker.

        Side Effects:
            - Закрывает ImageClientContainer через aclose()
            - Закрывает TextClientContainer через aclose()
            - Все HTTP-сессии внутри клиентов корректно завершаются
        """
        try:
            image_container = get_image_client_container()
            await image_container.aclose()
            self.logger.info("ImageClientContainer closed in WednesdayBot")
        except Exception as e:
            self.logger.warning(f"Error closing ImageClientContainer in WednesdayBot: {e}")

        try:
            text_container = get_text_client_container()
            await text_container.aclose()
            self.logger.info("TextClientContainer closed in WednesdayBot")
        except Exception as e:
            self.logger.warning(f"Error closing TextClientContainer in WednesdayBot: {e}")
