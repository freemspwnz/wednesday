"""Обработчик событий чата для Telegram бота."""

from __future__ import annotations

from typing import TYPE_CHECKING

from telegram import Bot, Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import ContextTypes

from shared.base.exceptions import ServiceError
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
                        # Используем rate limiting для защиты от превышения лимитов Telegram API
                        from shared.retry import retry_on_connect_error

                        rate_limiter = getattr(self.services, "telegram_api_rate_limiter", None)

                        async def _send_welcome() -> None:
                            await retry_on_connect_error(
                                self.bot.send_message,
                                chat_id=chat_id,
                                text=welcome,
                                max_retries=3,
                                delay=2.0,
                                handle_rate_limit=True,
                            )

                        if rate_limiter:
                            await rate_limiter.execute_with_rate_limit(_send_welcome)
                        else:
                            # Fallback без rate limiting (для обратной совместимости)
                            await _send_welcome()
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
                except ServiceError as add_error:
                    # Ошибки сервисного слоя
                    self.logger.error(
                        f"Ошибка сервиса при добавлении чата {chat_id}: {add_error}",
                        exc_info=True,
                    )
                except (KeyboardInterrupt, SystemExit, MemoryError, SystemError) as add_error:
                    # Критические ошибки - пробрасываем выше
                    self.logger.critical(
                        f"Критическая ошибка при добавлении чата {chat_id}: {add_error}",
                        exc_info=True,
                    )
                    raise
                except Exception as add_error:
                    # Неожиданные ошибки - логируем, но не прерываем работу
                    self.logger.error(
                        f"Неожиданная ошибка при добавлении чата {chat_id}: {add_error}",
                        exc_info=True,
                    )

            # Бот удалён из чата
            if new in {"left", "kicked"} and old in {"member", "administrator", "restricted"}:
                try:
                    await self.services.chats.remove_chat(chat_id)
                except ServiceError as remove_error:
                    # Ошибки сервисного слоя
                    self.logger.error(
                        f"Ошибка сервиса при удалении чата {chat_id}: {remove_error}",
                        exc_info=True,
                    )
                except (KeyboardInterrupt, SystemExit, MemoryError, SystemError) as remove_error:
                    # Критические ошибки - пробрасываем выше
                    self.logger.critical(
                        f"Критическая ошибка при удалении чата {chat_id}: {remove_error}",
                        exc_info=True,
                    )
                    raise
                except Exception as remove_error:
                    # Неожиданные ошибки - логируем, но не прерываем работу
                    self.logger.error(
                        f"Неожиданная ошибка при удалении чата {chat_id}: {remove_error}",
                        exc_info=True,
                    )

        except (KeyboardInterrupt, SystemExit, MemoryError, SystemError) as e:
            # Критические ошибки - пробрасываем выше
            self.logger.critical(f"Критическая ошибка в on_my_chat_member: {e}", exc_info=True)
            raise
        except Exception as e:
            # Неожиданные ошибки - логируем, но не прерываем работу
            self.logger.error(f"Неожиданная ошибка в on_my_chat_member: {e}", exc_info=True)
