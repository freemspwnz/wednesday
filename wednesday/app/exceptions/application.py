"""Ошибки прикладного сценария, не принадлежащие домену."""

from __future__ import annotations

from domain.chat import ChatId
from domain.user import UserId

from .base import AppError


class ChatNotFoundError(AppError):
    """Чат отсутствует в хранилище."""

    def __init__(self, chat_id: ChatId) -> None:
        self.chat_id = chat_id
        super().__init__(f"chat not found: {chat_id.value}")


class UserNotFoundError(AppError):
    """Пользователь отсутствует в хранилище."""

    def __init__(self, user_id: UserId) -> None:
        self.user_id = user_id
        super().__init__(f"user not found: {user_id}")
