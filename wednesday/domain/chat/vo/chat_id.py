from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from ..exceptions import ValidationError


@dataclass(frozen=True)
class ChatId:
    """Chat's ID."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise ValidationError("value must be UUID")

    @classmethod
    def new(cls) -> ChatId:
        return cls(value=uuid4())

    @classmethod
    def ensure(cls, chat_id: ChatId) -> ChatId:
        if not isinstance(chat_id, ChatId):
            raise ValidationError("chat_id must be a ChatId")
        return chat_id
