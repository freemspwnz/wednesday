"""
Резервный (поддерживающий) бот, который включается при остановке основного.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from telegram import Update
from telegram.error import NetworkError as _TNetworkError, TelegramError, TimedOut as _TTimedOut
from telegram.ext import Application, ChatMemberHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.base_handlers import BaseHandlers
from bot.bot_application_factory import create_telegram_application
from bot.bot_lifecycle_manager import BotLifecycleManager
from bot.chat_event_handler import ChatEventHandler
from infra.logging.logger import log_all_methods
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
    Использует минимальный SupportBotServices с только необходимыми зависимостями.
    """

    def __init__(
        self,
        services: SupportBotServices,
        telegram_config: BotTelegramConfig,
        request_start_main: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Инициализирует SupportBot.

        Создает экземпляр резервного бота, который работает когда основной бот остановлен.
        SupportBot предоставляет базовую функциональность: команды /help, /log и /start
        для запуска основного бота.

        Args:
            services: Контейнер сервисов для SupportBot (внедряется через DI).
            telegram_config: Конфигурация Telegram бота (внедряется через DI).
            request_start_main: Опциональный callback-функция для запроса запуска основного бота.
                Если None, запуск основного бота через /start будет недоступен.

        Raises:
            ValueError: Если services равен None.
        """
        if services is None:
            raise ValueError("services не может быть None. Передайте SupportBotServices через Dependency Injection.")

        # Инициализируем BaseHandlers с services (создает self.logger и self.admins_store)
        super().__init__(services)

        # Сохраняем ссылку на services для доступа к зависимостям
        self.services = services

        # Создаем Application через фабрику
        self.logger.info("Создание Application через фабрику")
        self.application: Application = create_telegram_application(telegram_config)
        self.request_start_main: Callable[[], Awaitable[None]] | None = request_start_main
        self.is_running: bool = False
        # Event для ожидания сигнала остановки (вместо busy-wait цикла)
        self._stop_event = asyncio.Event()

        # Настройки приложения для доступа к конфигурации через DI
        self.settings: AppSettings = services.settings

        # Инициализация менеджера жизненного цикла
        self.lifecycle_manager = BotLifecycleManager(self.logger)

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
        self.setup_handlers()

        # Запускаем PTB Application через lifecycle manager с warmup
        await self.lifecycle_manager.start_application(self.application, enable_warmup=True)

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
            self.is_running = False
            self._stop_event.set()  # Разблокирует await self._stop_event.wait() в start()

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

            # Останавливаем PTB Application через lifecycle manager
            await self.lifecycle_manager.stop_application(self.application)

            self.logger.info("SupportBot успешно остановлен")

        except Exception as e:
            self.logger.error(f"Ошибка при остановке SupportBot: {e}", exc_info=True)
        finally:
            # Гарантированное закрытие ресурсов (всегда выполняется)
            try:
                await self.services.cleanup()
                self.logger.info("Все ресурсы SupportBotServices закрыты")
            except Exception as cleanup_error:
                self.logger.warning(f"Ошибка при cleanup ресурсов: {cleanup_error}")

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
        Команда доступна только администраторам.

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

        # В админ-чате не отправляем статусное сообщение
        admin_chat_id = self.settings.admin_chat_id if self.settings else None
        is_admin_chat = False
        if admin_chat_id is not None and chat_id is not None:
            try:
                is_admin_chat = int(chat_id) == admin_chat_id
            except (ValueError, TypeError):
                pass

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
            except (TelegramError, _TNetworkError, _TTimedOut):
                pass

        # Сигнализируем раннеру/супервизору о необходимости запуска основного бота
        if self.request_start_main is not None:
            try:
                await self.request_start_main()
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
