from __future__ import annotations

from dataclasses import dataclass

from ...exceptions import InvalidStateTransitionError
from .base import ChatState


@dataclass(frozen=True)
class InactiveState(ChatState):
    """Value Object: inactive chat state."""

    @staticmethod
    def activate() -> ChatState:
        from .active import ActiveState

        return ActiveState()

    @staticmethod
    def deactivate() -> ChatState:
        raise InvalidStateTransitionError("cannot deactivate inactive chat")
