"""Фабрика для создания PTB Application."""

from __future__ import annotations

from telegram.ext import Application
from telegram.request import HTTPXRequest

from bot.bot_constants import (
    CONNECT_TIMEOUT_SECONDS,
    CONNECTION_POOL_SIZE,
    POOL_TIMEOUT_SECONDS,
    READ_TIMEOUT_SECONDS,
)
from shared.config import BotTelegramConfig


def create_telegram_application(telegram_config: BotTelegramConfig) -> Application:
    """Создает и конфигурирует PTB Application.

    Инкапсулирует логику создания HTTPXRequest и Application с валидацией токена.
    Обеспечивает единообразное создание Application для всех ботов.

    Args:
        telegram_config: Конфигурация Telegram бота (внедряется через DI).

    Returns:
        Настроенный экземпляр Application с HTTPXRequest.

    Raises:
        ValueError: Если токен бота не установлен в конфигурации.
    """
    # Валидация токена
    telegram_token: str = telegram_config.bot_token or ""
    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN должен быть установлен. Проверьте конфигурацию.")

    # Создание HTTPXRequest с общими константами
    request: HTTPXRequest = HTTPXRequest(
        connection_pool_size=CONNECTION_POOL_SIZE,
        pool_timeout=POOL_TIMEOUT_SECONDS,
        read_timeout=READ_TIMEOUT_SECONDS,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
    )

    # Создание и возврат Application
    return Application.builder().token(telegram_token).request(request).build()
