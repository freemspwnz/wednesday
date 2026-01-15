"""Обработчик событий чата для Telegram бота."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Bot, Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

from app.chat_info_service import ChatInfoService
from bot.handlers.messages import WELCOME_MESSAGE_CHAT
from shared.bot_services import BotServices
from shared.protocols.infrastructure import ILogger
from shared.retry import retry_on_connect_error

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
        if services.chat_event_service is None:
            raise ValueError("chat_event_service must be provided in BotServices")
        if services.telegram_api_rate_limiter is None:
            raise ValueError("telegram_api_rate_limiter must be provided in BotServices")
        self._chat_event_service = services.chat_event_service
        # Сохраняем в локальную переменную для типизации mypy
        self._rate_limiter = services.telegram_api_rate_limiter

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

            # Определяем изменение статуса через сервис
            status_change = ChatInfoService.determine_bot_status_change(old, new)

            # Бот добавлен/активирован в чате
            if status_change.was_added:
                # Делегируем обработку события в сервис
                await self._chat_event_service.handle_bot_added(chat_id)

                # Отправляем приветственное сообщение
                welcome = WELCOME_MESSAGE_CHAT
                try:

                    async def _send_welcome() -> None:
                        await retry_on_connect_error(
                            self.bot.send_message,
                            chat_id=chat_id,
                            text=welcome,
                            max_retries=3,
                            delay=2.0,
                            handle_rate_limit=True,
                        )

                    await self._rate_limiter.execute_with_rate_limit(_send_welcome)
                except (TelegramError, NetworkError, TimedOut) as send_error:
                    # Временные сетевые ошибки - можно повторить позже
                    self.logger.warning(f"Не удалось отправить приветствие в чат {chat_id}: {send_error}")
                except (KeyboardInterrupt, SystemExit, MemoryError, SystemError) as send_error:
                    # Критические ошибки - пробрасываем выше
                    self.logger.critical(
                        f"Критическая ошибка при отправке приветствия в чат {chat_id}: {send_error}",
                        exc_info=True,
                    )
                    raise
                except Exception as send_error:
                    # Другие ошибки (например, бот заблокирован) - логируем, но не прерываем работу
                    self.logger.error(
                        f"Ошибка при отправке приветствия в чат {chat_id}: {send_error}",
                        exc_info=True,
                    )

            # Бот удалён из чата
            if status_change.was_removed:
                # Делегируем обработку события в сервис
                await self._chat_event_service.handle_bot_removed(chat_id)

        except (KeyboardInterrupt, SystemExit, MemoryError, SystemError) as e:
            # Критические ошибки - пробрасываем выше
            self.logger.critical(f"Критическая ошибка в on_my_chat_member: {e}", exc_info=True)
            raise
        except Exception as e:
            # Неожиданные ошибки - логируем, но не прерываем работу
            self.logger.error(f"Неожиданная ошибка в on_my_chat_member: {e}", exc_info=True)
