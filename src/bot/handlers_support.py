"""Обработчики команд для SupportBot."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from telegram import Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

from bot.base_handlers import BaseHandlers
from shared.bot_services import SupportBotServices
from shared.config import AppSettings
from shared.protocols import ILogger
from shared.retry import retry_on_connect_error

if TYPE_CHECKING:
    pass

# Константы для SupportBot
MAX_LOG_DAYS_SUPPORT = 10  # максимальное количество дней для команды /log в SupportBot


class SupportBotHandlers(BaseHandlers):
    """Обработчики команд для SupportBot.

    Инкапсулирует команды резервного бота: /start, /help, /log и обработчик
    неизвестных команд. Содержит полную реализацию всех методов.

    Использует композицию для доступа к зависимостям через SupportBotServices
    вместо прямого наследования от бота, что улучшает соблюдение SRP.
    """

    def __init__(
        self,
        services: SupportBotServices,
        logger: ILogger,
        request_start_main: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Инициализирует обработчики команд SupportBot.

        Args:
            services: Контейнер сервисов для SupportBot (внедряется через DI).
            logger: Экземпляр логгера для логирования операций.
            request_start_main: Опциональный callback-функция для запроса запуска основного бота.
                Если None, запуск основного бота через /start будет недоступен.
        """
        super().__init__(services, logger)
        self.request_start_main: Callable[[], Awaitable[None]] | None = request_start_main
        self.settings: AppSettings = services.settings

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
            except (TelegramError, NetworkError, TimedOut):
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
        except (TelegramError, NetworkError, TimedOut) as e:
            self.logger.warning(f"Ошибка при отправке help: {e}")

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
            user_id = update.effective_user.id if update.effective_user else None
            chat_id = update.effective_chat.id if update.effective_chat else None
            text = update.message.text if update.message else None
            self.logger.info(f"/unknown for SupportBot: user_id={user_id}, chat_id={chat_id}, text={text}")
        except Exception as log_error:
            # Обрабатываем ошибку логирования - не критично, но логируем для диагностики
            self.logger.warning(
                f"Не удалось залогировать информацию о неизвестной команде: {log_error}",
                exc_info=False,
            )
        try:
            await retry_on_connect_error(
                update.message.reply_text,
                "🛠 Технические работы. Основной бот временно недоступен. \nПожалуйста, попробуйте позже.",
                max_retries=3,
                delay=2.0,
            )
        except (TelegramError, NetworkError, TimedOut) as e:
            self.logger.warning(f"Не удалось отправить сообщение о техработах: {e}")
