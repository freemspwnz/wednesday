from ..base import AppError, UnexpectedAppError


class RetryError(AppError):
    """Base retry error."""


class UnexpectedRetryError(UnexpectedAppError):
    """Unexpected retry error."""
