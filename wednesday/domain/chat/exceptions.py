from ..kernel.exceptions import (
    AccessDeniedError,
    DomainError,
    InvalidStateTransitionError,
    StaleWriteError,
    ValidationError,
)


class ChatError(DomainError):
    """Errors from the chat bounded context."""


class ScheduleLimitExceededError(ChatError):
    """Exceeded the maximum number of schedules."""

    def __init__(self, max_schedules: int) -> None:
        super().__init__(f"schedules must be <= {max_schedules}")


__all__ = [
    "AccessDeniedError",
    "ChatError",
    "InvalidStateTransitionError",
    "ScheduleLimitExceededError",
    "StaleWriteError",
    "ValidationError",
]
