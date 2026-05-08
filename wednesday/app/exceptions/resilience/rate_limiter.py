from ..base import AppError, UnexpectedAppError


class RateLimitError(AppError):
    """Base rate limit error."""


class TooManyRequests(RateLimitError):
    """Too many requests."""

    def __init__(
        self,
        message: str = "Too many requests",
        *,
        retry_after: int | None = None,
        reset_at: float | None = None,
        remaining: int | None = None,
        limit_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.reset_at = reset_at
        self.remaining = remaining
        self.limit_name = limit_name


class UnexpectedRateLimitError(UnexpectedAppError):
    """Unexpected rate limit error."""
