from typing import Self

from ...exceptions import ValidationError


class ChatState:
    """Base class for chat states."""

    @staticmethod
    def activate() -> "ChatState":
        raise NotImplementedError

    @staticmethod
    def deactivate() -> "ChatState":
        raise NotImplementedError

    @classmethod
    def ensure(cls, state: Self) -> Self:
        if not isinstance(state, cls):
            raise ValidationError("state must be a ChatState")
        return state
