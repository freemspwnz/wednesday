"""Utilities shared by routers in this package (admin command parsing, replies)."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message

from app.exceptions import unwrap_exception
from app.protocols import Logger
from domain.kernel.exceptions import DomainError

from ..messages.exceptions import COMMAND_FAILURE, user_message_for_exception

T = TypeVar("T")

_BOT_MEMBER_STATUSES = frozenset({
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.RESTRICTED,
})


@dataclass(frozen=True, slots=True)
class _HandlerLogContext:
    started_event: str
    failed_event: str
    extra: dict[str, object]


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


def _command_module(message: Message) -> str:
    name = _command_name(message).lstrip("/").split("@", 1)[0]
    return name or "unknown"


def _callback_module(callback: CallbackQuery) -> str:
    raw = callback.data
    if not raw:
        return "callback"
    return raw.split(":", 1)[0]


async def is_bot_member_of_chat(bot: Bot, tg_chat_id: int) -> bool:
    """True if the bot is currently a member of the chat (not left/kicked)."""
    me = await bot.me()
    try:
        member = await bot.get_chat_member(chat_id=tg_chat_id, user_id=me.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    return member.status in _BOT_MEMBER_STATUSES


async def safe_callback_answer(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> bool:
    """Answer a callback query; return False when Telegram rejects it as stale."""
    try:
        if text is None:
            await callback.answer()
        else:
            await callback.answer(text, show_alert=show_alert)
    except TelegramBadRequest:
        return False
    return True


async def run_message_handler(
    message: Message,
    logger: Logger,
    action: Callable[[], Awaitable[T]],
) -> T | None:
    async def reply(text: str) -> None:
        await message.answer(text)

    return await _run_handler(
        logger.bind(module=_command_module(message)),
        action,
        log=_HandlerLogContext(
            started_event="Command handler started",
            failed_event="Command handler failed",
            extra={
                "command": _command_name(message),
                "user_id": message.from_user.id if message.from_user else None,
                "chat_id": message.chat.id if message.chat else None,
            },
        ),
        reply=reply,
    )


async def run_callback_handler(
    callback: CallbackQuery,
    logger: Logger,
    action: Callable[[], Awaitable[T]],
) -> T | None:
    async def reply(text: str) -> None:
        if await safe_callback_answer(callback, text, show_alert=True):
            return
        if not isinstance(callback.message, Message):
            return
        try:
            await callback.message.answer(text)
        except (TelegramBadRequest, TelegramForbiddenError):
            return

    return await _run_handler(
        logger.bind(module=_callback_module(callback)),
        action,
        log=_HandlerLogContext(
            started_event="Callback handler started",
            failed_event="Callback handler failed",
            extra={
                "callback_data": callback.data,
                "user_id": callback.from_user.id if callback.from_user else None,
                "chat_id": callback.message.chat.id if callback.message and callback.message.chat else None,
            },
        ),
        reply=reply,
    )


async def _run_handler(
    logger: Logger,
    action: Callable[[], Awaitable[T]],
    *,
    log: _HandlerLogContext,
    reply: Callable[[str], Awaitable[None]],
) -> T | None:
    logger.info(log.started_event, **log.extra)
    try:
        return await action()
    except Exception as exc:
        root = unwrap_exception(exc)
        text = user_message_for_exception(root) or COMMAND_FAILURE
        log_fn = logger.info if isinstance(root, DomainError) else logger.warning
        log_fn(log.failed_event, **log.extra, error_type=type(root).__name__, error=str(root))
        await reply(text)
        return None
