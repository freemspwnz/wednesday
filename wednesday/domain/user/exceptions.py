from ..kernel.exceptions import (
    AccessDeniedError,
    DomainError,
    InvalidStateTransitionError,
    ValidationError,
)


class UserBannedError(DomainError):
    """User is banned."""

    def __init__(self, message: str = "user is banned") -> None:
        super().__init__(message)


class UserNotBannedError(DomainError):
    """User is not banned."""

    def __init__(self, message: str = "user is not banned") -> None:
        super().__init__(message)


class LimitViolationError(DomainError):
    """Subscription limits exceeded."""

    def __init__(self, code: str, details: dict[str, int]) -> None:
        self.code = code
        self.details = details
        super().__init__(f"limit violation: {code}")


class CooldownViolationError(DomainError):
    """Cooldown not passed."""

    def __init__(self, code: str, details: dict[str, int]) -> None:
        self.code = code
        self.details = details
        super().__init__(f"cooldown violation: {code}")


class ManagementAccessDeniedError(AccessDeniedError):
    """Denied management action with typed code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class StaleWriteError(DomainError):
    """Command timestamp is older than aggregate clock."""

    def __init__(self, message: str = "stale write") -> None:
        super().__init__(message)


__all__ = [
    "AccessDeniedError",
    "CooldownViolationError",
    "DomainError",
    "InvalidStateTransitionError",
    "LimitViolationError",
    "ManagementAccessDeniedError",
    "StaleWriteError",
    "UserBannedError",
    "UserNotBannedError",
    "ValidationError",
]
