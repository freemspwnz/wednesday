from enum import StrEnum
from typing import Self

from ..exceptions import ValidationError


class ChatType(StrEnum):
    PRIVATE = "private"
    GROUP = "group"
    SUPERGROUP = "supergroup"
    CHANNEL = "channel"

    @classmethod
    def ensure(cls, chat_type: Self) -> Self:
        if not isinstance(chat_type, cls):
            raise ValidationError("chat_type must be a ChatType")
        return chat_type
