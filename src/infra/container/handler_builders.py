"""Билдеры PTB‑хендлеров и реестра обработчиков."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.bot_error_handler import BotErrorHandler
from bot.handlers.admin import AdminHandlers
from bot.handlers.chat_event import ChatEventHandler
from bot.handlers.models import ModelHandlers
from bot.handlers.registry import BotHandlersRegistry
from bot.handlers.user import UserHandlers
from shared.bot_services import BotServices
from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    from telegram import Bot
    from telegram.ext import Application


def build_user_handlers(
    *,
    services: BotServices,
    logger: ILogger,
) -> UserHandlers:
    """Создаёт обработчики пользовательских команд."""
    handlers_logger = logger.bind(module="UserHandlers")
    return UserHandlers(
        services=services,
        logger=handlers_logger,
    )


def build_admin_handlers(
    *,
    services: BotServices,
    logger: ILogger,
) -> AdminHandlers:
    """Создаёт обработчики административных команд."""
    handlers_logger = logger.bind(module="AdminHandlers")
    return AdminHandlers(
        services=services,
        logger=handlers_logger,
    )


def build_model_handlers(
    *,
    services: BotServices,
    logger: ILogger,
) -> ModelHandlers:
    """Создаёт обработчики команд управления моделями."""
    handlers_logger = logger.bind(module="ModelHandlers")
    return ModelHandlers(
        services=services,
        logger=handlers_logger,
    )


def build_chat_event_handler(
    *,
    services: BotServices,
    bot: Bot,
    logger: ILogger,
) -> ChatEventHandler:
    """Создаёт обработчик событий чата."""
    handler_logger = logger.bind(module="ChatEventHandler")
    return ChatEventHandler(
        services=services,
        bot=bot,
        logger=handler_logger,
    )


def build_error_handler(
    *,
    logger: ILogger,
) -> BotErrorHandler:
    """Создаёт глобальный обработчик ошибок."""
    handler_logger = logger.bind(module="BotErrorHandler")
    return BotErrorHandler(
        logger=handler_logger,
    )


def build_handlers_registry(
    *,
    application: Application,
    services: BotServices,
    bot: Bot,
    logger: ILogger,
) -> BotHandlersRegistry:
    """Создаёт `BotHandlersRegistry` и все необходимые PTB‑хендлеры."""
    log = logger.bind(module="HandlersRegistry")
    log.debug(
        "Начало сборки BotHandlersRegistry",
        event="container_build_handlers_start",
        status="started",
    )

    user_handlers = build_user_handlers(services=services, logger=logger)
    admin_handlers = build_admin_handlers(services=services, logger=logger)
    model_handlers = build_model_handlers(services=services, logger=logger)
    chat_event_handler = build_chat_event_handler(services=services, bot=bot, logger=logger)
    error_handler = build_error_handler(logger=logger)

    registry = BotHandlersRegistry(
        application=application,
        user_handlers=user_handlers,
        admin_handlers=admin_handlers,
        model_handlers=model_handlers,
        chat_event_handler=chat_event_handler,
        error_handler=error_handler,
        logger=log,
    )

    log.info(
        "BotHandlersRegistry успешно собран",
        event="container_build_handlers_success",
        status="ok",
    )

    return registry
