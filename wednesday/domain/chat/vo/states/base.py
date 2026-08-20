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
    def ensure(cls, state: object) -> Self:
        if not isinstance(state, cls):
            raise ValidationError(f"State must be an instance of {cls.__name__}")
        return state
