from ..kernel.exceptions import (
    AccessDeniedError,
    DomainError,
    InvalidStateTransitionError,
    StaleWriteError,
    ValidationError,
)


class UserError(DomainError):
    """Errors from the user bounded context."""


class UserNotFoundError(UserError):
    """User aggregate not found."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"user not found: {user_id}")


class UserBannedError(UserError):
    """User is banned."""

    def __init__(self, message: str = "user is banned") -> None:
        super().__init__(message)


class LimitViolationError(UserError):
    """Subscription limits exceeded."""

    def __init__(self, code: str, details: dict[str, int]) -> None:
        self.code = code
        self.details = details
        super().__init__(f"limit violation: {code}")


class CooldownViolationError(UserError):
    """Cooldown not passed."""

    def __init__(self, code: str, details: dict[str, int]) -> None:
        self.code = code
        self.details = details
        super().__init__(f"cooldown violation: {code}")


class ModelSelectionError(UserError):
    """Model selection error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"model selection error: {code}")


class ModelNotFoundError(UserError):
    """Model not found."""

    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(f"model not found: {model}")


__all__ = [
    "AccessDeniedError",
    "CooldownViolationError",
    "InvalidStateTransitionError",
    "LimitViolationError",
    "ModelNotFoundError",
    "ModelSelectionError",
    "StaleWriteError",
    "UserBannedError",
    "UserError",
    "UserNotFoundError",
    "ValidationError",
]
