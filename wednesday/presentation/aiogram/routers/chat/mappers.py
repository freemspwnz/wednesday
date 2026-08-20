"""Telegram → DTO mapping for in-chat commands."""

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import CallbackQuery, Message

from app.dto import ChatContext


def telegram_status_to_str(status: ChatMemberStatus) -> str:
    """Map Telegram membership status to string role."""
    if status == ChatMemberStatus.CREATOR:
        return "owner"
    if status == ChatMemberStatus.ADMINISTRATOR:
        return "admin"
    if status == ChatMemberStatus.MEMBER:
        return "member"
    if status == ChatMemberStatus.RESTRICTED:
        return "restricted"
    raise ValueError("unknown Telegram membership status")


async def resolve_chat_member(
    bot: Bot,
    event: Message | CallbackQuery,
    chat: ChatContext,
) -> tuple[int, str]:
    """Build domain actor for the caller; raise ValueError only on adapter failures."""
    caller = event.from_user
    if caller is None:
        msg = "Не удалось определить пользователя."
        raise ValueError(msg)

    try:
        member = await bot.get_chat_member(chat_id=chat.tg_id, user_id=caller.id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        msg = "Не удалось проверить участника в чате."
        raise ValueError(msg) from exc

    role = telegram_status_to_str(member.status)

    return caller.id, role
