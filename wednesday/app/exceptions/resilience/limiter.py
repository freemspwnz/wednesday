from ..base import AppError, UnexpectedAppError


class LimitError(AppError):
    """Base rate limit error."""


class TooManyRequests(LimitError):
    """Too many requests."""

    def __init__(
        self,
        message: str = "Too many requests",
        *,
        retry_after: int,
        reset_at: float,
        remaining: int | None = None,
        limit: str,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.reset_at = reset_at
        self.remaining = remaining
        self.limit = limit


class LimitStorageError(LimitError):
    """Rate limiter storage backend error."""


class UnexpectedLimitError(UnexpectedAppError):
    """Unexpected rate limit error."""
