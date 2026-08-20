"""Filters for in-chat command handlers."""

from typing import ClassVar

from aiogram.enums import ChatType
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject


class GroupChatFilter(BaseFilter):
    """Passes for group/supergroup chats (Telegram update chat type)."""

    _GROUP_CHAT_TYPES: ClassVar[frozenset[ChatType]] = frozenset({ChatType.GROUP, ChatType.SUPERGROUP})

    async def __call__(self, event: TelegramObject) -> bool:
        chat = None
        if isinstance(event, Message):
            chat = event.chat
        elif isinstance(event, CallbackQuery) and isinstance(event.message, Message):
            chat = event.message.chat
        if chat is None:
            return False
        return chat.type in self._GROUP_CHAT_TYPES
