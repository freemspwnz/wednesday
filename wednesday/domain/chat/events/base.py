from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import ValidationError
from ..vo import AwareDatetime, ChatId


@dataclass(frozen=True)
class ChatEvent:
    chat_id: ChatId
    occurred_at: AwareDatetime

    def __post_init__(self) -> None:
        ChatId.ensure(self.chat_id)
        AwareDatetime.ensure(self.occurred_at)

    @classmethod
    def ensure(cls, event: ChatEvent) -> ChatEvent:
        if not isinstance(event, cls):
            raise ValidationError("event must be a ChatEvent")
        return event
