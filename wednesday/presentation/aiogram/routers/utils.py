"""Utilities shared by routers in this package (admin command parsing, replies)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message

from app.exceptions import unwrap_exception
from app.protocols import Logger

from ..messages.exceptions import COMMAND_FAILURE, user_message_for_exception

T = TypeVar("T")

_BOT_MEMBER_STATUSES = frozenset({
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.RESTRICTED,
})


def parse_telegram_id(raw: str) -> int:
    value = raw.strip()
    if value.startswith("@"):
        msg = "Укажите числовой Telegram ID, не username"
        raise ValueError(msg)
    try:
        return int(value)
    except ValueError as exc:
        msg = "Укажите целочисленный Telegram ID"
        raise ValueError(msg) from exc


def parse_positive_int(raw: str) -> int:
    try:
        value = int(raw.strip())
    except ValueError as exc:
        msg = "Укажите целое число"
        raise ValueError(msg) from exc
    if value < 1:
        msg = "Число должно быть не меньше 1"
        raise ValueError(msg)
    return value


def _command_name(message: Message) -> str:
    text = message.text or ""
    return text.split()[0] if text else "/unknown"


async def is_bot_member_of_chat(bot: Bot, tg_chat_id: int) -> bool:
    """True if the bot is currently a member of the chat (not left/kicked)."""
    me = await bot.me()
    try:
        member = await bot.get_chat_member(chat_id=tg_chat_id, user_id=me.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    return member.status in _BOT_MEMBER_STATUSES


async def run_message_handler(
    message: Message,
    logger: Logger,
    action: Callable[[], Awaitable[T]],
) -> T | None:
    async def reply(text: str) -> None:
        await message.answer(text)

    return await _run_handler(
        logger,
        action,
        log_event="Command handler failed",
        log_extra={"command": _command_name(message)},
        reply=reply,
    )


async def run_callback_handler(
    callback: CallbackQuery,
    logger: Logger,
    action: Callable[[], Awaitable[T]],
) -> T | None:
    async def reply(text: str) -> None:
        await callback.answer(text, show_alert=True)

    return await _run_handler(
        logger,
        action,
        log_event="Callback handler failed",
        log_extra={"callback_data": callback.data},
        reply=reply,
    )


async def _run_handler(
    logger: Logger,
    action: Callable[[], Awaitable[T]],
    *,
    log_event: str,
    log_extra: dict[str, object],
    reply: Callable[[str], Awaitable[None]],
) -> T | None:
    try:
        return await action()
    except Exception as exc:
        root = unwrap_exception(exc)
        text = user_message_for_exception(root) or COMMAND_FAILURE
        logger.warning(log_event, **log_extra, error_type=type(root).__name__, error=str(root))
        await reply(text)
        return None
