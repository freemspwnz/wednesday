"""Билдеры инфраструктурных messaging‑сервисов (IMessagingService)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from infra.messaging.ptb import PTBMessagingService
from shared.protocols.messaging import IMessagingService

if TYPE_CHECKING:
    from telegram import Bot


def build_ptb_messaging_service(bot: Bot) -> IMessagingService:
    """Создаёт реализацию `IMessagingService` на базе python‑telegram‑bot.

    Args:
        bot: Экземпляр Telegram `Bot`, уже созданный в Composition Root.

    Returns:
        Экземпляр `IMessagingService`, реализованный через PTB.
    """
    return PTBMessagingService(bot=bot)
