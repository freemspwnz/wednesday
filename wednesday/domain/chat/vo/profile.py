from dataclasses import dataclass
from typing import ClassVar, Self

from ..exceptions import ValidationError
from .type import ChatType


@dataclass(frozen=True)
class ChatProfile:
    """Value Object: chat profile."""

    NEED_TITLE_OR_USERNAME: ClassVar[set[ChatType]] = {
        ChatType.CHANNEL,
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    }

    _MAX_TITLE_LENGTH: ClassVar[int] = 255
    _MAX_USERNAME_LENGTH: ClassVar[int] = 32

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
        if self.title and len(self.title) > self._MAX_TITLE_LENGTH:
            raise ValidationError("Chat title too long")
        if self.username and len(self.username) > self._MAX_USERNAME_LENGTH:
            raise ValidationError("Chat username too long")

    @classmethod
    def ensure(cls, profile: object) -> Self:
        if not isinstance(profile, cls):
            raise ValidationError(f"Profile must be an instance of {cls.__name__}")
        return profile
