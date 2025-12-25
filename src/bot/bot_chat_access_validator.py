"""Валидатор доступа к чатам для бота."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from shared.protocols import ILogger

if TYPE_CHECKING:
    from telegram import Bot

# Константы для таймаутов
TIMEOUT_MEDIUM_SECONDS = 30.0


class BotChatAccessValidator:
    """Валидирует доступность чатов для бота.

    Выполняет проверку доступа к чату перед запуском бота.
    Использует увеличенный таймаут для более надежной проверки.
    """

    def __init__(self, logger: ILogger, timeout: float = TIMEOUT_MEDIUM_SECONDS) -> None:
        """Инициализирует валидатор доступа к чатам.

        Args:
            logger: Экземпляр логгера для логирования.
            timeout: Таймаут для проверки доступа к чату в секундах.
        """
        self.logger = logger
        self.timeout = timeout

    async def validate_chat_access(self, bot: Bot, chat_id: str | None) -> None:
        """Проверяет доступность чата для отправки сообщений.

        Выполняет проверку доступа к чату, указанному в chat_id, перед запуском.
        Использует увеличенный таймаут для более надежной проверки. Предупреждения
        логируются, но не блокируют запуск бота.

        Args:
            bot: Экземпляр Telegram Bot для проверки доступа.
            chat_id: ID чата для проверки (может быть None).

        Side Effects:
            - Вызывает bot.get_chat() для получения информации о чате.
            - Логирует результат проверки или предупреждения при ошибках.
            - Не блокирует запуск бота при ошибках, только предупреждает.

        Raises:
            TimeoutError: Если проверка заняла больше timeout секунд.
            Exception: При других ошибках доступа к чату (логируется, но не пробрасывается).
        """
        if chat_id is None:
            self.logger.warning("Chat ID не задан, проверка доступа пропущена")
            return

        try:
            # Пытаемся получить информацию о чате с увеличенным таймаутом
            chat_info = await asyncio.wait_for(
                bot.get_chat(chat_id),
                timeout=self.timeout,
            )
            self.logger.info(f"Чат доступен: {chat_info.title or chat_info.first_name}")
        except TimeoutError:
            self.logger.warning(f"Таймаут при проверке доступа к чату {chat_id}")
            self.logger.warning("Возможно, проблемы с сетью или Telegram API")
            self.logger.warning("Бот будет работать, но проверка доступа к чату не выполнена")
        except Exception as e:
            self.logger.warning(f"Не удалось получить доступ к чату {chat_id}: {e}")
            self.logger.warning("Бот будет работать, но не сможет отправлять сообщения в указанный чат")
            self.logger.warning("Убедитесь, что:")
            self.logger.warning("1. CHAT_ID указан правильно")
            self.logger.warning("2. Бот добавлен в чат/канал")
            self.logger.warning("3. У бота есть права на отправку сообщений")
