"""Обработчик событий чата для Telegram бота."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Bot, Update
from telegram.ext import ContextTypes

from shared.bot_services import BotServices
from shared.protocols import ILogger

if TYPE_CHECKING:
    pass


class ChatEventHandler:
    """Обработчик событий изменения статуса бота в чатах.

    Обрабатывает события, когда бот добавляется или удаляется из чата.
    Автоматически добавляет чат в список рассылки при добавлении бота и
    удаляет при удалении бота из чата.
    """

    def __init__(
        self,
        services: BotServices,
        bot: Bot,
        logger: ILogger,
    ) -> None:
        """Инициализирует обработчик событий чата.

        Args:
            services: Контейнер сервисов бота для доступа к репозиториям.
            bot: Экземпляр Telegram Bot для отправки сообщений.
            logger: Экземпляр логгера для логирования операций.
        """
        self.services = services
        self.bot = bot
        self.logger = logger

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
                try:
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
                        await self.bot.send_message(chat_id=chat_id, text=welcome)
                    except Exception as send_error:
                        self.logger.warning(f"Не удалось отправить приветствие в чат {chat_id}: {send_error}")
                except Exception as add_error:
                    self.logger.error(
                        f"Не удалось добавить чат {chat_id} в список рассылки: {add_error}",
                        exc_info=True,
                    )

            # Бот удалён из чата
            if new in {"left", "kicked"} and old in {"member", "administrator", "restricted"}:
                try:
                    await self.services.chats.remove_chat(chat_id)
                except Exception as remove_error:
                    self.logger.error(
                        f"Не удалось удалить чат {chat_id} из списка рассылки: {remove_error}",
                        exc_info=True,
                    )

        except Exception as e:
            self.logger.error(f"Критическая ошибка в on_my_chat_member: {e}", exc_info=True)
