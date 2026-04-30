from ..kernel.exceptions import (
    AccessDeniedError,
    DomainError,
    InvalidStateTransitionError,
    ValidationError,
)
from .policies import LimitViolation


class UserBannedError(DomainError):
    """Пользователь забанен."""


class UserNotBannedError(DomainError):
    """Пользователь не забанен."""


class LimitViolationError(DomainError):
    """Нарушение политики лимитов."""

    def __init__(self, violation: LimitViolation) -> None:
        self.violation = violation


__all__ = [
    "AccessDeniedError",
    "DomainError",
    "InvalidStateTransitionError",
    "LimitViolationError",
    "UserBannedError",
    "UserNotBannedError",
    "ValidationError",
]
