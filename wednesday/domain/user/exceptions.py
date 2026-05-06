from ..kernel.exceptions import (
    AccessDeniedError,
    DomainError,
    InvalidStateTransitionError,
    ValidationError,
)


class UserBannedError(DomainError):
    """Пользователь забанен."""

    def __init__(self, message: str = "user is banned") -> None:
        super().__init__(message)


class UserNotBannedError(DomainError):
    """Пользователь не забанен."""

    def __init__(self, message: str = "user is not banned") -> None:
        super().__init__(message)


class LimitViolationError(DomainError):
    """Нарушение политики лимитов."""

    def __init__(self, code: str, details: dict[str, int]) -> None:
        self.code = code
        self.details = details
        super().__init__(f"limit violation: {code}")


class CooldownViolationError(DomainError):
    """Нарушение generation cоoldown."""

    def __init__(self, code: str, details: dict[str, int]) -> None:
        self.code = code
        self.details = details
        super().__init__(f"cooldown violation: {code}")


__all__ = [
    "AccessDeniedError",
    "CooldownViolationError",
    "DomainError",
    "InvalidStateTransitionError",
    "LimitViolationError",
    "UserBannedError",
    "UserNotBannedError",
    "ValidationError",
]
