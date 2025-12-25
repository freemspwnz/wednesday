"""
Резервный (поддерживающий) бот, который включается при остановке основного.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from telegram import Update
from telegram.error import NetworkError as _TNetworkError, TelegramError, TimedOut as _TTimedOut
from telegram.ext import Application, ChatMemberHandler, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from bot.base_handlers import BaseHandlers
from bot.bot_state_coordinator import BotStateCoordinator, BotStateData
from bot.chat_event_handler import ChatEventHandler

# Константы для магических чисел (импортируем из wednesday_bot для консистентности)
from bot.wednesday_bot import (
    CONNECT_TIMEOUT_SECONDS,
    CONNECTION_POOL_SIZE,
    POOL_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
)
from infra.logging.logger import log_all_methods
from infra.rate_limiting import RateLimiter
from shared.bot_services import SupportBotServices
from shared.config import AppSettings, BotTelegramConfig
from shared.retry import retry_on_connect_error

if TYPE_CHECKING:
    pass

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
    _safe_reply_text) и консистентности с другими хендлерами.
    Использует минимальный BotServices (только с settings и rate_limiter).
    """

    def __init__(
        self,
        services: SupportBotServices,
        telegram_config: BotTelegramConfig,
        request_start_main: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        """Инициализирует SupportBot.

        Создает экземпляр резервного бота, который работает когда основной бот остановлен.
        SupportBot предоставляет базовую функциональность: команды /help, /log и /start
        для запуска основного бота.

        Args:
            services: Контейнер сервисов для SupportBot (внедряется через DI).
            telegram_config: Конфигурация Telegram бота (внедряется через DI).
            request_start_main: Опциональный callback-функция для запроса запуска основного бота.
                Принимает словарь с метаданными (chat_id, message_id) для редактирования статусного
                сообщения. Если None, запуск основного бота через /start будет недоступен.

        Raises:
            ValueError: Если services равен None.
        """
        if services is None:
            raise ValueError("services не может быть None. Передайте SupportBotServices через Dependency Injection.")

        # Инициализируем BaseHandlers с services (создает self.logger и self.admins_store)
        super().__init__(services)

        # Сохраняем ссылку на services для доступа к зависимостям
        self.services = services

        # Создаем HTTPXRequest для PTB Application
        request: HTTPXRequest = HTTPXRequest(
            connection_pool_size=CONNECTION_POOL_SIZE,
            pool_timeout=POOL_TIMEOUT_SECONDS,
            read_timeout=READ_TIMEOUT_SECONDS,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
        )
        # telegram_config.bot_token передается через DI
        telegram_token: str = telegram_config.bot_token or ""
        assert telegram_token, "TELEGRAM_BOT_TOKEN должен быть установлен"
        self.application: Application = Application.builder().token(telegram_token).request(request).build()
        self.request_start_main: Callable[[dict[str, Any]], Awaitable[None]] | None = request_start_main
        self.is_running: bool = False
        # Event для ожидания сигнала остановки (вместо busy-wait цикла)
        self._stop_event = asyncio.Event()
        # Данные для редактирования сообщения об остановке основного
        self.pending_shutdown_edit: dict[str, Any] | None = None
        # Данные для цепочки запуска основного: сообщение "Запускаю..."
        self.pending_startup_edit: dict[str, Any] | None = None

        # Лимитер на основе Redis для административных команд SupportBot
        # (например, /log), чтобы избежать случайного "забивания" лог‑канала.
        # В случае недоступности Redis лимитер автоматически работает в in‑memory
        # режиме и не блокирует админа.
        self.rate_limiter: RateLimiter = RateLimiter(
            redis_client=services.redis_client,
            prefix="rate:support:",
            window=60,
            limit=20,
        )
        # Настройки приложения для доступа к конфигурации через DI
        self.settings: AppSettings = services.settings

        # Инициализация state coordinator для координации с основным ботом
        admin_chat_id_int = self.settings.admin_chat_id if self.settings else None
        self.state_coordinator = BotStateCoordinator(
            logger=self.logger,
            admin_chat_id=admin_chat_id_int,
        )

        # Инициализация обработчика событий чата для синхронизации списка чатов
        self.chat_event_handler = ChatEventHandler(
            services=self.services,
            bot=self.application.bot,
            logger=self.logger,
        )

    def setup_handlers(self) -> None:
        """Настраивает обработчики команд для SupportBot.

        Регистрирует команды:
        - /start - запуск основного бота
        - /help - справка по резервному боту
        - /log - отправка логов администратору
        - Обработчик неизвестных команд для сообщений о техработах
        - Обработчик событий изменения статуса бота в чатах
        """
        self.application.add_handler(CommandHandler("start", self.start_main_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("log", self.log_command))
        # Любые неизвестные команды – сообщение о техработах
        self.application.add_handler(MessageHandler(filters.COMMAND, self.maintenance_message))
        # Обработчик событий изменения статуса бота в чатах
        self.application.add_handler(
            ChatMemberHandler(
                self.chat_event_handler.on_my_chat_member,
                ChatMemberHandler.MY_CHAT_MEMBER,
            ),
        )

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
        if isinstance(self.pending_shutdown_edit, dict):
            state_data = BotStateData(
                chat_id=self.pending_shutdown_edit.get("chat_id"),
                message_id=self.pending_shutdown_edit.get("message_id"),
            )
            await self.state_coordinator.handle_support_startup_edit(
                bot=self.application.bot,
                state_data=state_data,
            )

        # Сообщим админам о запуске SupportBot
        try:
            admins = await self.admins_store.list_all_admins()
            for admin_id in admins:
                try:
                    await retry_on_connect_error(
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
        self._stop_event.clear()
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            self.logger.info("Получен сигнал отмены для основного цикла SupportBot")
            self.is_running = False
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
        self._stop_event.set()  # Разблокирует await self._stop_event.wait() в start()
        # Если был запуск основного через статусное сообщение — добавим строку про остановку Support Bot
        if isinstance(self.pending_startup_edit, dict):
            state_data = BotStateData(
                chat_id=self.pending_startup_edit.get("chat_id"),
                message_id=self.pending_startup_edit.get("message_id"),
            )
            await self.state_coordinator.handle_support_shutdown_edit(
                bot=self.application.bot,
                state_data=state_data,
            )
            # Очистим ссылку, чтобы не переиспользовать
            self.pending_startup_edit = None
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
                        await retry_on_connect_error(
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
            await retry_on_connect_error(
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
            - Проверяет права администратора через admins_store.is_admin().
        """
        await self._send_logs_command(update, context, max_days=MAX_LOG_DAYS_SUPPORT)

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
            await retry_on_connect_error(
                update.message.reply_text,
                "❌ Доступно только администратору",
                max_retries=3,
                delay=2.0,
            )
            return

        # В админ-чате не отправляем изменяемое статусное сообщение
        admin_chat_id = self.settings.admin_chat_id if self.settings else None
        is_admin_chat = BotStateCoordinator.is_admin_chat(chat_id, admin_chat_id)

        # Отправляем статусное сообщение только если это не админ-чат
        status_msg = None
        if not is_admin_chat:
            try:
                status_msg = await retry_on_connect_error(
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
            await retry_on_connect_error(
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
            await retry_on_connect_error(
                update.message.reply_text,
                help_text,
                max_retries=3,
                delay=2.0,
            )
        except (TelegramError, _TNetworkError, _TTimedOut) as e:
            self.logger.warning(f"Ошибка при отправке help: {e}")
