from ..base import AppError, UnexpectedAppError


class RetryError(AppError):
    """Base retry error."""


class MaxAttemptsExhaustedError(RetryError):
    """Max attempts exhausted error."""

    def __init__(
        self,
        attempts: int,
        message: str = "Max attempts exhausted",
    ) -> None:
        super().__init__(message)
        self.attempts = attempts


class UnexpectedRetryError(UnexpectedAppError):
    """Unexpected retry error."""
