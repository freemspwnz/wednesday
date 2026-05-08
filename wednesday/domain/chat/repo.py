from __future__ import annotations

from typing import Protocol

from .chat import Chat
from .vo import ChatId


class ChatRepo(Protocol):
    """Chat repository protocol."""

    async def get_by_id(self, chat_id: ChatId) -> Chat | None:
        """Get chat by ID."""
        ...

    async def save(self, chat: Chat) -> None:
        """Save chat."""
        ...

    async def exists(self, chat_id: ChatId) -> bool:
        """Check if chat exists."""
        ...
