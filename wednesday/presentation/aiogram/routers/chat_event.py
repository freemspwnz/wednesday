"""Chat event handlers: bot added to or removed from a chat."""

from __future__ import annotations

import random

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import ChatMemberUpdated

from app.protocols import Logger, RequestScope
from domain.chat import System
from domain.kernel.exceptions import InvalidStateTransitionError
from domain.kernel.vo import AwareDatetime

from ..messages import events as event_msg
from ..middlewares.utils import CHAT_MEMBER_LEFT_STATUSES

chat_event_router = Router(name="chat_event")

_GREETING_CHAT_TYPES = frozenset({"group", "supergroup"})


@chat_event_router.my_chat_member()
async def on_my_chat_member(
    event: ChatMemberUpdated,
    bot: Bot,
    logger: Logger,
    scope: RequestScope,
) -> None:
    """Bot added/removed to/from chat."""
    log = logger.bind(module="my_chat_member")
    status = event.new_chat_member.status
    log.info("My chat member event", status=status)

    if status in CHAT_MEMBER_LEFT_STATUSES:
        chat = await scope.registration_uc.find_chat_by_tg_id(tg_id=event.chat.id)
        if chat is not None and chat.id is not None:
            try:
                await scope.chat_commands_uc.deactivate(
                    chat_id=chat.id,
                    actor=System(),
                    at=AwareDatetime.now_utc(),
                )
                log.info("Chat deactivated after bot left", tg_chat_id=event.chat.id)
            except InvalidStateTransitionError:
                log.debug("Chat already inactive", tg_chat_id=event.chat.id)
            except Exception:
                log.warning(
                    "Failed to deactivate chat after bot left",
                    tg_chat_id=event.chat.id,
                    exc_info=True,
                )
        return

    if status == ChatMemberStatus.MEMBER:
        try:
            await bot.send_message(chat_id=event.chat.id, text=event_msg.BOT_ADDED_TO_CHAT)
        except TelegramForbiddenError:
            log.warning("Cannot send message to chat", chat_id=event.chat.id)


@chat_event_router.chat_member()
async def on_chat_member(
    event: ChatMemberUpdated,
    bot: Bot,
    logger: Logger,
) -> None:
    """Chat member added/removed."""
    log = logger.bind(module="chat_member")
    status = event.new_chat_member.status
    log.info("Chat member event", status=status)

    if event.chat.type not in _GREETING_CHAT_TYPES:
        return

    if status == ChatMemberStatus.MEMBER:
        text = random.choice(event_msg.MEMBER_JOINED)
        try:
            await bot.send_message(chat_id=event.chat.id, text=text)
        except TelegramForbiddenError:
            log.warning("Cannot send message to chat", chat_id=event.chat.id)

    if status in CHAT_MEMBER_LEFT_STATUSES:
        text = random.choice(event_msg.MEMBER_LEFT)
        try:
            await bot.send_message(chat_id=event.chat.id, text=text)
        except TelegramForbiddenError:
            log.warning("Cannot send message to chat", chat_id=event.chat.id)
