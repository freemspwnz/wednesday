from __future__ import annotations

from enum import StrEnum

from ..exceptions import ValidationError


class ChatType(StrEnum):
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"

    @classmethod
    def ensure(cls, chat_type: ChatType) -> ChatType:
        if not isinstance(chat_type, cls):
            raise ValidationError("chat_type must be a ChatType")
        return chat_type
