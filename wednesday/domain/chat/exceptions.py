from ..kernel.exceptions import (
    AccessDeniedError,
    DomainError,
    InvalidStateTransitionError,
    StaleWriteError,
    ValidationError,
)


class ChatError(DomainError):
    """Errors from the chat bounded context."""


class ChatNotFoundError(ChatError):
    """Chat aggregate not found."""

    def __init__(self, chat_id: str) -> None:
        self.chat_id = chat_id
        super().__init__(f"chat not found: {chat_id}")


class ScheduleLimitExceededError(ChatError):
    """Exceeded the maximum number of schedules."""

    def __init__(self, max_schedules: int) -> None:
        super().__init__(f"schedules must be <= {max_schedules}")


__all__ = [
    "AccessDeniedError",
    "ChatError",
    "ChatNotFoundError",
    "InvalidStateTransitionError",
    "ScheduleLimitExceededError",
    "StaleWriteError",
    "ValidationError",
]
