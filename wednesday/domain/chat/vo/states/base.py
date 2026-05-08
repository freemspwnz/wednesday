from __future__ import annotations

from ...exceptions import ValidationError


class ChatState:
    """Base class for chat states."""

    @staticmethod
    def activate() -> ChatState:
        raise NotImplementedError

    @staticmethod
    def deactivate() -> ChatState:
        raise NotImplementedError

    @classmethod
    def ensure(cls, state: ChatState) -> ChatState:
        if not isinstance(state, cls):
            raise ValidationError("state must be a ChatState")
        return state
