"""Application-layer errors."""


class AppError(Exception):
    """Base class for all application-layer errors."""


class UnexpectedAppError(AppError):
    """Unexpected application error."""
