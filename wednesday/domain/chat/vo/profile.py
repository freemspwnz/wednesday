from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from ..exceptions import ValidationError
from .type import ChatType

MAX_TITLE_LENGTH = 255
MAX_USERNAME_LENGTH = 32


@dataclass(frozen=True)
class ChatProfile:
    """Value Object: chat profile."""

    NEED_TITLE_OR_USERNAME: ClassVar[set[ChatType]] = {
        ChatType.CHANNEL,
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }

    type: ChatType
    telegram_id: int
    title: str | None = None
    username: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, ChatType):
            raise ValidationError("Chat type must be a ChatType")
        if self.telegram_id == 0:
            raise ValidationError("Chat Telegram ID must be non-zero")
        if self.type in self.NEED_TITLE_OR_USERNAME and not (self.title or self.username):
            raise ValidationError("public chat needs title or username")
        if self.title and len(self.title) > MAX_TITLE_LENGTH:
            raise ValidationError("Chat title too long")
        if self.username and len(self.username) > MAX_USERNAME_LENGTH:
            raise ValidationError("Chat username too long")

    @classmethod
    def ensure(cls, profile: ChatProfile) -> ChatProfile:
        if not isinstance(profile, cls):
            raise ValidationError("profile must be a ChatProfile")
        return profile
