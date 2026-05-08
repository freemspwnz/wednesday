from __future__ import annotations

from dataclasses import dataclass

from ...exceptions import InvalidStateTransitionError
from .base import ChatState


@dataclass(frozen=True)
class ActiveState(ChatState):
    """Value Object: active chat state."""

    @staticmethod
    def activate() -> ChatState:
        raise InvalidStateTransitionError("cannot activate already active chat")

    @staticmethod
    def deactivate() -> ChatState:
        from .inactive import InactiveState

        return InactiveState()
