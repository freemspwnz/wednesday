"""Chat membership events (bot / member join-leave)."""

import random

from aiogram import Bot, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import ChatMemberUpdated

from app.protocols import Logger, RequestScope

from ...messages import chat as chat_msg
from ...middlewares.utils import CHAT_MEMBER_LEFT_STATUSES

chat_member_router = Router(name="chat_member")

_GREETING_CHAT_TYPES = frozenset({"group", "supergroup"})


@chat_member_router.my_chat_member()
async def on_my_chat_member(
    event: ChatMemberUpdated,
    bot: Bot,
    logger: Logger,
    scope: RequestScope,
) -> None:
    """Bot added/removed to/from chat."""
    at = event.date
    log = logger.bind(module="my_chat_member")
    status = event.new_chat_member.status
    log.info("My chat member event", status=status)

    if status in CHAT_MEMBER_LEFT_STATUSES:
        await scope.chat_management_uc.on_bot_kicked(
            tg_id=event.chat.id,
            at=at,
        )
        return

    if status == ChatMemberStatus.MEMBER:
        try:
            await bot.send_message(chat_id=event.chat.id, text=chat_msg.BOT_ADDED_TO_CHAT)
        except TelegramForbiddenError:
            log.warning("Cannot send message to chat", chat_id=event.chat.id)


@chat_member_router.chat_member()
async def on_chat_member(
    event: ChatMemberUpdated,
    bot: Bot,
    logger: Logger,
) -> None:
    """Chat member added/removed greetings."""
    log = logger.bind(module="chat_member")
    status = event.new_chat_member.status
    log.info("Chat member event", status=status)

    if event.chat.type not in _GREETING_CHAT_TYPES:
        return

    if status == ChatMemberStatus.MEMBER:
        text = random.choice(chat_msg.MEMBER_JOINED)
        try:
            await bot.send_message(chat_id=event.chat.id, text=text)
        except TelegramForbiddenError:
            log.warning("Cannot send message to chat", chat_id=event.chat.id)

    if status in CHAT_MEMBER_LEFT_STATUSES:
        text = random.choice(chat_msg.MEMBER_LEFT)
        try:
            await bot.send_message(chat_id=event.chat.id, text=text)
        except TelegramForbiddenError:
            log.warning("Cannot send message to chat", chat_id=event.chat.id)
