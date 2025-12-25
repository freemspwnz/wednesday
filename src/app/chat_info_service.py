"""Application service для получения информации о чатах Telegram."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from shared.base.base_service import BaseService
from shared.protocols import ILogger

if TYPE_CHECKING:
    from telegram import Bot, Chat

# Константы для таймаутов
DEFAULT_CHAT_INFO_TIMEOUT = 5.0
DEFAULT_CHAT_FULL_TIMEOUT = 10.0


class ChatInfoService(BaseService):
    """Сервис для безопасного получения информации о чатах Telegram.

    Инкапсулирует логику получения информации о чатах через Telegram Bot API
    с обработкой ошибок и таймаутов. Предоставляет единый интерфейс для всех
    компонентов приложения, соблюдая архитектурные границы.
    """

    def __init__(
        self,
        bot: Bot,
        *,
        logger: ILogger,
    ) -> None:
        """Инициализирует сервис получения информации о чатах.

        Args:
            bot: Экземпляр Telegram Bot для получения информации о чатах.
            logger: Экземпляр логгера.
        """
        super().__init__(logger)
        self._bot = bot

    async def get_chat_info_safe(
        self,
        chat_id: int,
        timeout: float = DEFAULT_CHAT_INFO_TIMEOUT,
    ) -> tuple[int, str]:
        """Безопасно получает информацию о чате с обработкой ошибок.

        Args:
            chat_id: ID чата для получения информации.
            timeout: Таймаут для запроса в секундах.

        Returns:
            Кортеж (chat_id, title), где title - название чата или сообщение об ошибке.
        """
        from telegram.error import NetworkError, TelegramError, TimedOut

        try:
            chat_info = await asyncio.wait_for(
                self._bot.get_chat(chat_id),
                timeout=timeout,
            )
            title = getattr(chat_info, "title", getattr(chat_info, "first_name", "Unknown"))
            return (chat_id, title)
        except (TelegramError, NetworkError, TimedOut) as e:
            self.logger.warning(f"Не удалось получить информацию о чате {chat_id}: {e}")
            return (chat_id, f"не удалось получить информацию: {type(e).__name__}")
        except TimeoutError:
            self.logger.warning(f"Таймаут при получении информации о чате {chat_id}")
            return (chat_id, "таймаут при получении информации")
        except (ValueError, TypeError, AttributeError) as e:
            # Ошибки валидации данных из getattr или других операций
            self.logger.warning(f"Ошибка валидации данных для чата {chat_id}: {e}")
            return (chat_id, "ошибка валидации данных")

    async def get_chat_safe(
        self,
        chat_id: int,
        timeout: float = DEFAULT_CHAT_FULL_TIMEOUT,
    ) -> Chat | None:
        """Безопасно получает полный объект чата с обработкой ошибок и таймаутом.

        Args:
            chat_id: ID чата для получения информации.
            timeout: Таймаут для запроса в секундах (по умолчанию 10 секунд).

        Returns:
            Объект чата или None в случае ошибки.
        """
        from telegram.error import NetworkError, TelegramError, TimedOut

        try:
            chat_info = await asyncio.wait_for(
                self._bot.get_chat(chat_id),
                timeout=timeout,
            )
            return chat_info
        except (TelegramError, NetworkError, TimedOut) as e:
            self.logger.warning(f"Не удалось получить информацию о чате {chat_id}: {e}")
            return None
        except TimeoutError:
            self.logger.warning(f"Таймаут при получении информации о чате {chat_id}")
            return None
        except (ValueError, TypeError, AttributeError) as e:
            # Ошибки валидации данных
            self.logger.warning(f"Ошибка валидации данных для чата {chat_id}: {e}")
            return None
