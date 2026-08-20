"""Filters for in-chat command handlers."""

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.dto import ChatContext


class GroupChatFilter(BaseFilter):
    """Passes when registration middleware provided a group or supergroup chat."""

    async def __call__(
        self,
        event: TelegramObject,
        chat: ChatContext | None = None,
    ) -> bool:
        if not isinstance(chat, ChatContext):
            return False
        return chat.type in {"group", "supergroup"}
