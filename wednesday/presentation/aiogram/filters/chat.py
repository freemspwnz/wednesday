"""Filters for in-chat command handlers."""

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject

from app.dto import ChatContext
from domain.chat import ChatType


class GroupChatFilter(BaseFilter):
    """Passes when registration middleware provided a group or supergroup chat."""

    async def __call__(
        self,
        event: TelegramObject,
        chat: ChatContext | None = None,
    ) -> bool:
        if not isinstance(chat, ChatContext):
            return False
        return chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}
