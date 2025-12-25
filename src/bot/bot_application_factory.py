"""Фабрика для создания PTB Application."""

from __future__ import annotations

from telegram.ext import Application
from telegram.request import HTTPXRequest

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

    # Создание HTTPXRequest с настройками из конфигурации
    request: HTTPXRequest = HTTPXRequest(
        connection_pool_size=telegram_config.connection_pool_size,
        pool_timeout=telegram_config.pool_timeout,
        read_timeout=telegram_config.read_timeout,
        connect_timeout=telegram_config.connect_timeout,
    )

    # Создание и возврат Application
    return Application.builder().token(telegram_token).request(request).build()
