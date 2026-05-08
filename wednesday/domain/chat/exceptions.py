from ..kernel.exceptions import (
    AccessDeniedError,
    DomainError,
    InvalidStateTransitionError,
    StaleWriteError,
    ValidationError,
)


class ScheduleLimitExceededError(DomainError):
    """Exceeded the maximum number of schedules."""

    def __init__(self, max_schedules: int) -> None:
        super().__init__(f"schedules must be <= {max_schedules}")


class ManagementAccessDeniedError(AccessDeniedError):
    """Management access denied."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"management access denied: {code}")


__all__ = [
    "DomainError",
    "InvalidStateTransitionError",
    "ManagementAccessDeniedError",
    "ScheduleLimitExceededError",
    "StaleWriteError",
    "ValidationError",
]
