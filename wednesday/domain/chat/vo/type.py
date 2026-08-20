from enum import StrEnum
from typing import Self

from ..exceptions import ValidationError


class ChatType(StrEnum):
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"

    @classmethod
    def ensure(cls, chat_type: object) -> Self:
        if not isinstance(chat_type, cls):
            raise ValidationError(f"chat_type must be an instance of {cls.__name__}")
        return chat_type
