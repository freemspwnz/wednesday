"""Application-layer errors not belonging to the domain."""

from __future__ import annotations

from domain.chat import ChatId
from domain.user import UserId

from .base import AppError


class ChatNotFoundError(AppError):
    """Chat is not found in the storage."""

    def __init__(self, chat_id: ChatId) -> None:
        self.chat_id = chat_id
        super().__init__(f"chat not found: {chat_id.value}")


class UserNotFoundError(AppError):
    """User is not found in the storage."""

    def __init__(self, user_id: UserId) -> None:
        self.user_id = user_id
        super().__init__(f"user not found: {user_id}")
