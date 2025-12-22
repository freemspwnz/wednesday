"""
Резервный (поддерживающий) бот, который включается при остановке основного.
"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.error import NetworkError as _TNetworkError, TelegramError, TimedOut as _TTimedOut
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from bot.base_handlers import BaseHandlers

# Константы для магических чисел (импортируем из wednesday_bot для консистентности)
from bot.wednesday_bot import (
    CONNECT_TIMEOUT_SECONDS,
    CONNECTION_POOL_SIZE,
    POOL_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
)
from infra.logging.logger import get_logger, log_all_methods
from infra.rate_limiting import RateLimiter
from shared.config_v2 import AppSettings, ConfigV2
from shared.protocols import IRateLimiter

# Создаём экземпляр ConfigV2 при импорте модуля
config: ConfigV2 = ConfigV2()

# Константы для SupportBot
MAX_POLLING_ATTEMPTS = 4  # максимальное количество попыток запуска polling
LAST_POLLING_ATTEMPT_INDEX = 3  # индекс последней попытки (0-based: 3 = 4-я попытка)
MAX_LOG_DAYS_SUPPORT = 10  # максимальное количество дней для команды /log в SupportBot


@log_all_methods()
class SupportBot(BaseHandlers):
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

    Использует AppSettings для доступа к настройкам приложения через DI,
    вместо прямого чтения из глобального config.

    Наследуется от BaseHandlers для использования общих методов (_send_log_file,
    _retry_on_connect_error, _safe_reply_text) и консистентности с другими хендлерами.
    Использует минимальный BotServices (только с settings и rate_limiter).
    """

    def __init__(self, request_start_main: Callable[[dict[str, Any]], Awaitable[None]] | None = None) -> None:
        """Инициализирует SupportBot.

        Создает экземпляр резервного бота, который работает когда основной бот остановлен.
        SupportBot предоставляет базовую функциональность: команды /help, /log и /start
        для запуска основного бота.

        Args:
            request_start_main: Опциональный callback-функция для запроса запуска основного бота.
                Принимает словарь с метаданными (chat_id, message_id) для редактирования статусного
                сообщения. Если None, запуск основного бота через /start будет недоступен.
        """
        # Сначала создаем все необходимые компоненты для BotServices
        request: HTTPXRequest = HTTPXRequest(
            connection_pool_size=CONNECTION_POOL_SIZE,
            pool_timeout=POOL_TIMEOUT_SECONDS,
            read_timeout=READ_TIMEOUT_SECONDS,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
        )
        # config.telegram_token проверяется в _validate_required_vars, поэтому не может быть None
        telegram_token: str = config.telegram_token or ""
        assert telegram_token, "TELEGRAM_BOT_TOKEN должен быть установлен"
        self.application: Application = Application.builder().token(telegram_token).request(request).build()
        self.request_start_main: Callable[[dict[str, Any]], Awaitable[None]] | None = request_start_main
        self.is_running: bool = False
        # Данные для редактирования сообщения об остановке основного
        self.pending_shutdown_edit: dict[str, Any] | None = None
        # Данные для цепочки запуска основного: сообщение "Запускаю..."
        self.pending_startup_edit: dict[str, Any] | None = None
        # Лимитер на основе Redis для административных команд SupportBot
        # (например, /log), чтобы избежать случайного "забивания" лог‑канала.
        # В случае недоступности Redis лимитер автоматически работает в in‑memory
        # режиме и не блокирует админа.
        from infra.redis.redis_client import get_redis

        redis_client = get_redis()
        self.rate_limiter: RateLimiter = RateLimiter(
            redis_client=redis_client, prefix="rate:support:", window=60, limit=20
        )
        # Настройки приложения для доступа к конфигурации через DI
        self.settings: AppSettings = AppSettings()
        # Создаем минимальный BotServices только с settings для использования BaseHandlers
        # SupportBot не использует остальные сервисы, поэтому передаем заглушки для обязательных полей
        from app.frog_limit_service import FrogRateLimiterService
        from app.frog_requests import FrogRequestService
        from shared.bot_services import BotServices

        # Создаём общий логгер для всех сервисов
        app_logger = get_logger("app")

        # Создаём rate limiters для команды /frog
        SECONDS_PER_MINUTE = 60
        global_limiter: IRateLimiter = RateLimiter(
            redis_client=redis_client,
            prefix="frog:global:",
            window=self.settings.frog_rate_limit_window_seconds,
            limit=self.settings.frog_rate_limit_max_requests,
        )
        user_limiter: IRateLimiter = RateLimiter(
            redis_client=redis_client,
            prefix="frog:user:",
            window=self.settings.frog_rate_limit_minutes * SECONDS_PER_MINUTE,
            limit=1,
        )

        frog_rate_limiter = FrogRateLimiterService(
            settings=self.settings,
            global_limiter=global_limiter,
            user_limiter=user_limiter,
            logger=app_logger,
        )
        from infra.celery.celery_task_queue import CeleryTaskQueue

        task_queue = CeleryTaskQueue()
        frog_request_service = FrogRequestService(task_queue=task_queue, logger=app_logger)
        services: BotServices = BotServices(
            usage=None,  # type: ignore[arg-type]
            chats=None,  # type: ignore[arg-type]
            dispatch_registry=None,  # type: ignore[arg-type]
            metrics=None,  # type: ignore[arg-type]
            prompt_cache=None,  # type: ignore[arg-type]
            user_state_store=None,  # type: ignore[arg-type]
            settings=self.settings,
            image_service=None,  # type: ignore[arg-type]
            frog_rate_limiter=frog_rate_limiter,
            frog_request_service=frog_request_service,
            bot_controller=None,
        )
        # Инициализируем BaseHandlers с services (создает self.logger и self.admins_store)
        super().__init__(services)

    def setup_handlers(self) -> None:
        """Настраивает обработчики команд для SupportBot.

        Регистрирует команды:
        - /start - запуск основного бота
        - /help - справка по резервному боту
        - /log - отправка логов администратору
        - Обработчик неизвестных команд для сообщений о техработах
        """
        self.application.add_handler(CommandHandler("start", self.start_main_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("log", self.log_command))
        # Любые неизвестные команды – сообщение о техработах
        self.application.add_handler(MessageHandler(filters.COMMAND, self.maintenance_message))

    async def start(self) -> None:
        """Запускает SupportBot и начинает обработку команд.

        Инициализирует приложение с повторными попытками при сетевых ошибках,
        запускает polling и обрабатывает статусные сообщения от основного бота.

        Side Effects:
            - Инициализирует приложение через application.initialize().
            - Запускает polling через updater.start_polling().
            - Редактирует сообщение об остановке основного бота (если было передано).
            - Отправляет уведомления администраторам о запуске SupportBot.
            - Запускает основной цикл ожидания.

        Raises:
            TimedOut: Если не удалось установить соединение после всех попыток.
            NetworkError: Если возникли проблемы с сетью при инициализации.
            Conflict: Если не удалось запустить polling из-за конфликта getUpdates.
        """
        self.logger.info("Запуск бота-поддержки (SupportBot)")
        self.setup_handlers()

        # Все зависимости доступны через экземпляр SupportBot, bot_data больше не используется для DI

        # Этап 1: initialize с ретраями
        init_attempts = 4
        backoff = 2.0
        for attempt in range(1, init_attempts + 1):
            try:
                await self.application.initialize()
                self.logger.info("SupportBot: initialize() успешно")
                # Дополнительно «разогреем» бота, чтобы гарантированно установить контекст
                try:
                    _ = await self.application.bot.get_me()
                except Exception as warmup_err:
                    # Не фейлим старт из-за warmup; просто залогируем
                    self.logger.warning(f"SupportBot warmup get_me() не удался: {warmup_err}", exc_info=True)
                break
            except (_TTimedOut, _TNetworkError) as e:
                self.logger.warning(
                    f"SupportBot: сеть недоступна при initialize (попытка {attempt}/{init_attempts}): {e}",
                )
                if attempt == init_attempts:
                    raise
                await asyncio.sleep(backoff)
                backoff *= 1.5

        # Этап 2: start с ретраями (без повторного initialize)
        start_attempts = 3
        backoff = 2.0
        for attempt in range(1, start_attempts + 1):
            try:
                await self.application.start()
                self.logger.info("SupportBot: start() успешно")
                break
            except (_TTimedOut, _TNetworkError) as e:
                self.logger.warning(f"SupportBot: сеть недоступна при start (попытка {attempt}/{start_attempts}): {e}")
                if attempt == start_attempts:
                    raise
                await asyncio.sleep(backoff)
                backoff *= 1.5
            except RuntimeError as re:
                # Обработка случая: "ExtBot is not properly initialized"
                msg = str(re)
                if "ExtBot is not properly initialized" in msg:
                    self.logger.warning("SupportBot: повторная инициализация после ошибки ExtBot not initialized")
                    try:
                        await self.application.initialize()
                        # Повторный warmup
                        try:
                            _ = await self.application.bot.get_me()
                        except Exception:
                            pass
                    except Exception as reinit_err:
                        self.logger.warning(
                            f"SupportBot: не удалось повторно инициализировать приложение: {reinit_err}",
                            exc_info=True,
                        )
                    # Ретраим без немедленного падения
                    if attempt == start_attempts:
                        raise
                    await asyncio.sleep(backoff)
                    backoff *= 1.5
                else:
                    raise
        # Безопасный запуск polling с ретраями на случай конфликта getUpdates
        import asyncio as _asyncio

        from telegram.error import Conflict as _TGConflict

        delay = 2.0
        for attempt in range(4):
            try:
                updater = self.application.updater
                if updater:
                    await updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
                self.logger.info("SupportBot polling запущен")
                break
            except _TGConflict as e:
                self.logger.warning(f"Conflict при запуске polling SupportBot (попытка {attempt + 1}/4): {e}")
                if attempt == LAST_POLLING_ATTEMPT_INDEX:
                    raise
                await _asyncio.sleep(delay)
                delay *= 1.5

        # Если есть сообщение о статусе остановки — редактируем его на финальное (кроме админ-чата)
        try:
            if isinstance(self.pending_shutdown_edit, dict):
                chat_id = self.pending_shutdown_edit.get("chat_id")
                message_id = self.pending_shutdown_edit.get("message_id")
                # Пропускаем редактирование, если это админ-чат
                skip_admin_edit = False
                try:
                    if self.settings.admin_chat_id and chat_id is not None:
                        try:
                            skip_admin_edit = int(str(self.settings.admin_chat_id)) == int(str(chat_id))
                        except (ValueError, TypeError, AttributeError):
                            skip_admin_edit = False
                except (ValueError, TypeError, AttributeError):
                    skip_admin_edit = False

                if chat_id and message_id and not skip_admin_edit:
                    # Компактный финальный текст для не-админ чатов
                    final_text = "🛑  Wednesday Frog Bot остановлен\n✅ Резервный бот запущен"
                    try:
                        await self.application.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=final_text,
                        )
                        self.logger.info("Сообщение об остановке обновлено в чате-источнике")
                    except (TelegramError, _TNetworkError, _TTimedOut) as edit_err:
                        # Игнорируем ошибку "Message is not modified" — это нормально, если текст уже установлен
                        error_str = str(edit_err).lower()
                        if "message is not modified" in error_str or "not modified" in error_str:
                            self.logger.debug("Сообщение уже имеет нужный текст, пропускаем редактирование")
                        else:
                            self.logger.warning(f"Не удалось обновить сообщение об остановке: {edit_err}")
                elif chat_id and skip_admin_edit:
                    self.logger.info("SupportBot: пропускаю редактирование статусного сообщения в админском чате")
        except Exception as e:
            self.logger.warning(f"Не удалось обновить сообщение об остановке: {e}", exc_info=True)

        # Сообщим админам о запуске SupportBot
        try:
            admins = await self.admins_store.list_all_admins()
            for admin_id in admins:
                try:
                    await self._retry_on_connect_error(
                        self.application.bot.send_message,
                        chat_id=admin_id,
                        text=(
                            "🟢 SupportBot запущен и принимает команды.\n"
                            "• /help — справка\n• /log — последний лог\n• /start — запустить основной бот"
                        ),
                        max_retries=3,
                        delay=2.0,
                    )
                except (TelegramError, _TNetworkError, _TTimedOut):
                    pass
        except Exception:
            pass

        self.is_running = True
        try:
            while self.is_running:
                await asyncio.sleep(0.1)
        finally:
            self.logger.info("SupportBot основной цикл завершен")

    async def stop(self) -> None:
        """Останавливает SupportBot и освобождает ресурсы.

        Корректно завершает работу бота, останавливает polling, обновляет
        статусные сообщения и отправляет уведомления администраторам.

        Side Effects:
            - Устанавливает флаг is_running в False.
            - Редактирует статусное сообщение о запуске основного бота.
            - Останавливает updater через updater.stop().
            - Отправляет уведомления администраторам об остановке.
            - Останавливает приложение через application.stop().
        """
        if not self.is_running:
            return
        self.logger.info("Остановка бота-поддержки")
        self.is_running = False
        # Если был запуск основного через статусное сообщение — добавим строку про остановку Support Bot
        try:
            if isinstance(self.pending_startup_edit, dict):
                chat_id = self.pending_startup_edit.get("chat_id")
                message_id = self.pending_startup_edit.get("message_id")
                # Пропускаем для админского чата
                is_admin_chat = False
                try:
                    if self.settings.admin_chat_id and chat_id is not None:
                        try:
                            is_admin_chat = int(str(self.settings.admin_chat_id)) == int(str(chat_id))
                        except (ValueError, TypeError, AttributeError):
                            is_admin_chat = False
                except (ValueError, TypeError, AttributeError):
                    is_admin_chat = False
                if chat_id and message_id and not is_admin_chat:
                    interim_text = "🚀 Запускаю основной бот...\n🛑 Support Bot остановлен"
                    try:
                        await self.application.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=interim_text,
                        )
                    except (TelegramError, _TNetworkError, _TTimedOut):
                        pass
                # Очистим ссылку, чтобы не переиспользовать
                self.pending_startup_edit = None
        except Exception:
            pass
        # Сначала останавливаем polling, чтобы освободить соединения
        try:
            if hasattr(self.application, "updater") and self.application.updater:
                await self.application.updater.stop()
        except Exception as e:
            self.logger.warning(f"Ошибка при остановке updater'а SupportBot: {e}", exc_info=True)
        # Короткая пауза, чтобы соединения вернулись в пул
        try:
            await asyncio.sleep(0.2)
        except Exception:
            pass
        # Уведомим админов об остановке
        try:
            admins = await self.admins_store.list_all_admins()
            if admins:
                for admin_id in admins:
                    try:
                        await self._retry_on_connect_error(
                            self.application.bot.send_message,
                            chat_id=admin_id,
                            text=(
                                "🛑 SupportBot остановлен.\n\n"
                                "Если это не плановая остановка, проверьте логи и состояние основного бота."
                            ),
                            max_retries=3,
                            delay=2.0,
                        )
                    except (TelegramError, _TNetworkError, _TTimedOut):
                        pass
        except Exception:
            pass
        try:
            await self.application.stop()
        except Exception as e:
            self.logger.warning(f"Ошибка при остановке приложения SupportBot: {e}", exc_info=True)

        # Завершаем жизненный цикл приложения, освобождая все ресурсы PTB
        try:
            await self.application.shutdown()
        except Exception as e:
            self.logger.warning(f"Ошибка при shutdown приложения SupportBot: {e}", exc_info=True)

    async def maintenance_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик неизвестных команд.

        Отправляет сообщение о технических работах в ответ на любые
        неизвестные команды, так как SupportBot работает только когда
        основной бот остановлен.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Отправляет сообщение о техработах пользователю.
            - Логирует информацию о неизвестной команде.
        """
        if not update.message:
            return

        try:
            user_id = update.effective_user.id if update and update.effective_user else None
            chat_id = update.effective_chat.id if update and update.effective_chat else None
            text = update.message.text if update and update.message else None
            self.logger.info(f"/unknown for SupportBot: user_id={user_id}, chat_id={chat_id}, text={text}")
        except Exception:
            pass
        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                "🛠 Технические работы. Основной бот временно недоступен. \nПожалуйста, попробуйте позже.",
                max_retries=3,
                delay=2.0,
            )
        except (TelegramError, _TNetworkError, _TTimedOut) as e:
            self.logger.warning(f"Не удалось отправить сообщение о техработах: {e}")

    async def _is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором.

        Использует `self.admins_store` из `BaseHandlers` для проверки прав администратора.

        Args:
            user_id: ID пользователя Telegram для проверки прав администратора.

        Returns:
            True если пользователь является администратором, False в противном случае.
        """
        return await self.admins_store.is_admin(user_id)

    async def log_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /log.

        Отправляет логи администратору. Без аргумента отправляет последний файл,
        с аргументом [count] отправляет логи за N дней (1..10).
        Команда доступна только администраторам и защищена rate limiting.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении,
                пользователе и чате, из которого отправлена команда.
            context: Контекст бота, предоставляющий доступ к аргументам команды
                через context.args и к боту для отправки файлов через context.bot.

        Side Effects:
            - Читает файлы логов из директории logs/.
            - Отправляет файлы логов в чат через context.bot.send_document().
            - Проверяет права администратора через _is_admin().
        """
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        self.logger.info(f"SupportBot /log от user_id={user_id}, chat_id={chat_id}")
        if not await self._is_admin(user_id):
            await self._retry_on_connect_error(
                update.message.reply_text,
                "❌ Доступно только администратору",
                max_retries=3,
                delay=2.0,
            )
            return

        try:
            logs_dir = Path("logs")
            if not logs_dir.exists():
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "📭 Папка logs пуста или отсутствует",
                    max_retries=3,
                    delay=2.0,
                )
                return

            # Аргумент count
            count = 1
            capped_note = None
            if context.args and len(context.args) > 0:
                raw = context.args[0]
                if not raw.isdigit():
                    await self._retry_on_connect_error(
                        update.message.reply_text,
                        "❌ Неверный аргумент. Используйте: /log [count], где count — число 1..10",
                        max_retries=3,
                        delay=2.0,
                    )
                    return
                count = int(raw)
                if count > MAX_LOG_DAYS_SUPPORT:
                    count = MAX_LOG_DAYS_SUPPORT
                    capped_note = f"(ограничено максимумом {MAX_LOG_DAYS_SUPPORT} дней)"

            # Выбираем файлы по датам
            from datetime import datetime, timedelta

            wanted_dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(count)]
            selected: list[Path] = []
            for ds in wanted_dates:
                log_path = logs_dir / f"wednesday_bot_{ds}.log"
                zip_path = logs_dir / f"wednesday_bot_{ds}.log.zip"
                if log_path.exists():
                    selected.append(log_path)
                elif zip_path.exists():
                    selected.append(zip_path)

            if not selected:
                log_files = [p for p in logs_dir.iterdir() if p.is_file()]
                selected = sorted(log_files, key=lambda p: p.stat().st_mtime, reverse=True)[:1]

            if not selected:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    "📭 Нет логов для отправки",
                    max_retries=3,
                    delay=2.0,
                )
                return

            await self._retry_on_connect_error(
                update.message.reply_text,
                f"📦 Отправляю файл(ы) логов за {len(selected)} дн. {capped_note or ''}",
                max_retries=3,
                delay=2.0,
            )
            for lf in sorted(selected, key=lambda p: p.name):
                self.logger.info(f"SupportBot отправляет лог-файл: {lf.name} ({lf.stat().st_size} bytes)")
                try:
                    # Используем _send_log_file из BaseHandlers для отправки лог-файла
                    await self._send_log_file(
                        bot=context.bot,
                        chat_id=update.effective_chat.id,
                        path=lf,
                    )
                    self.logger.info("SupportBot: лог отправлен успешно")
                except (TelegramError, _TNetworkError, _TTimedOut) as e:
                    self.logger.warning(f"Ошибка при отправке лога {lf}: {e}")
            await self._retry_on_connect_error(
                update.message.reply_text,
                "✅ Готово",
                max_retries=3,
                delay=2.0,
            )
        except Exception as e:
            self.logger.error(f"Ошибка в команде /log: {e}", exc_info=True)
            try:
                await self._retry_on_connect_error(
                    update.message.reply_text,
                    f"❌ Ошибка при отправке логов: {str(e)[:200]}",
                    max_retries=3,
                    delay=2.0,
                )
            except (TelegramError, _TNetworkError, _TTimedOut):
                pass

    async def start_main_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start.

        Запускает основной бот (WednesdayBot) и выключает SupportBot.
        Команда доступна только администраторам. После выполнения команды
        запрос на запуск основного бота передается супервизору через
        request_start_main callback.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении,
                пользователе и чате, из которого отправлена команда.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Проверяет права администратора через _is_admin().
            - Отправляет статусное сообщение "Запускаю основной бот..." (кроме админ-чата).
            - Сохраняет метаданные сообщения для последующего редактирования.
            - Вызывает request_start_main() для передачи запроса супервизору.
        """
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        self.logger.info(f"SupportBot /start от user_id={user_id}, chat_id={chat_id}")
        if not await self._is_admin(user_id):
            await self._retry_on_connect_error(
                update.message.reply_text,
                "❌ Доступно только администратору",
                max_retries=3,
                delay=2.0,
            )
            return

        # В админ-чате не отправляем изменяемое статусное сообщение
        is_admin_chat = False
        try:
            if self.settings.admin_chat_id and chat_id is not None:
                try:
                    is_admin_chat = int(str(self.settings.admin_chat_id)) == int(str(chat_id))
                except (ValueError, TypeError, AttributeError):
                    is_admin_chat = False
        except (ValueError, TypeError, AttributeError):
            is_admin_chat = False

        # Отправляем статусное сообщение только если это не админ-чат
        status_msg = None
        if not is_admin_chat:
            try:
                status_msg = await self._retry_on_connect_error(
                    update.message.reply_text,
                    "🚀 Запускаю основной бот...",
                    max_retries=3,
                    delay=2.0,
                )
                if status_msg:
                    self.logger.info(f"SupportBot /start сообщение статусное: message_id={status_msg.message_id}")
                    # Сохраним ссылку, чтобы при остановке SupportBot дополнить текст строкой о его остановке
                    try:
                        self.pending_startup_edit = {
                            "chat_id": update.effective_chat.id,
                            "message_id": status_msg.message_id,
                        }
                    except (ValueError, TypeError, AttributeError):
                        self.pending_startup_edit = None
            except (TelegramError, _TNetworkError, _TTimedOut):
                pass

        # Сигнализируем раннеру/супервизору о необходимости запуска основного бота
        if self.request_start_main is not None:
            try:
                # В админ-чате не передаём payload для последующего редактирования
                payload = {}
                if (not is_admin_chat) and (status_msg is not None):
                    payload = {"chat_id": update.effective_chat.id, "message_id": status_msg.message_id}
                await self.request_start_main(payload)
                self.logger.info("SupportBot запрос запуска основного отправлен супервизору")
                # Не редактируем статусное сообщение сразу; финальный текст поставит основной бот после запуска
            except Exception as e:
                self.logger.error(f"Ошибка при запросе запуска основного бота: {e}", exc_info=True)
        else:
            self.logger.warning("request_start_main не задан, невозможно запустить основной бот")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help.

        Показывает справку по резервному боту (SupportBot) со списком доступных команд.
        Команда доступна только администраторам.

        Args:
            update: Объект обновления Telegram, содержащий информацию о сообщении
                и пользователе, который отправил команду.
            context: Контекст бота (не используется напрямую, но требуется
                для совместимости с интерфейсом обработчиков команд).

        Side Effects:
            - Проверяет права администратора через _is_admin().
            - Отправляет справку пользователю.
        """
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user_id = update.effective_user.id
        chat_id = update.effective_chat.id
        self.logger.info(f"SupportBot /help от user_id={user_id}, chat_id={chat_id}")
        if not await self._is_admin(user_id):
            await self._retry_on_connect_error(
                update.message.reply_text,
                "❌ Доступно только администратору",
                max_retries=3,
                delay=2.0,
            )
            return
        help_text = (
            "🛠 Справка по резервному боту (SupportBot)\n\n"
            "Доступные команды:\n"
            "• /help — эта справка\n"
            "• /log [count] — отправить логи за N дней (1..10), без аргумента — последний файл (только админ)\n"
            "• /start — запустить основной бот и выключить резервный (только админ)\n\n"
            "Поведение по умолчанию: любая неизвестная команда — сообщение о техработах."
        )
        try:
            await self._retry_on_connect_error(
                update.message.reply_text,
                help_text,
                max_retries=3,
                delay=2.0,
            )
        except (TelegramError, _TNetworkError, _TTimedOut) as e:
            self.logger.warning(f"Ошибка при отправке help: {e}")
