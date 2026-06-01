"""Telegram → domain mapping for in-chat commands."""

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Message

from app.dto import ChatContext
from domain.chat import ChatMember, ChatMemberId, ChatMemberRole


def telegram_status_to_chat_member_role(status: ChatMemberStatus) -> ChatMemberRole | None:
    """Map Telegram membership status to domain role (no access policy)."""
    if status == ChatMemberStatus.CREATOR:
        return ChatMemberRole.OWNER
    if status == ChatMemberStatus.ADMINISTRATOR:
        return ChatMemberRole.ADMIN
    if status == ChatMemberStatus.MEMBER:
        return ChatMemberRole.MEMBER
    if status == ChatMemberStatus.RESTRICTED:
        return ChatMemberRole.RESTRICTED
    return None


async def resolve_chat_member(
    bot: Bot,
    message: Message,
    chat: ChatContext,
) -> ChatMember:
    """Build domain ChatMember for the caller; raise ValueError only on adapter failures."""
    caller = message.from_user
    if caller is None:
        msg = "Не удалось определить пользователя."
        raise ValueError(msg)

    try:
        member = await bot.get_chat_member(chat_id=chat.tg_id, user_id=caller.id)
    except (TelegramBadRequest, TelegramForbiddenError) as exc:
        msg = "Не удалось проверить участника в чате."
        raise ValueError(msg) from exc

    role = telegram_status_to_chat_member_role(member.status)
    if role is None:
        msg = "Вы не являетесь активным участником этого чата."
        raise ValueError(msg)

    return ChatMember(
        id=ChatMemberId(caller.id),
        role=role,
        chat_id=chat.id,
    )
