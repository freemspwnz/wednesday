"""Cache access errors, mapped to Redis adapter failures."""

from ..base import AppError, UnexpectedAppError


class CacheError(AppError):
    """Base exception for cache persistence errors."""


class CacheBackendError(CacheError):
    """Base cache backend error with operation specification."""

    def __init__(self, message: str, *, operation: str) -> None:
        super().__init__(message)
        self.operation = operation


class CacheUnavailableError(CacheError):
    """Cache is temporarily unavailable (network, pool, Redis overload)."""

    def __init__(self, message: str, *, operation: str) -> None:
        super().__init__(message)
        self.operation = operation


class CacheTimeoutError(CacheError):
    """Cache operation exceeded socket/client timeout."""

    def __init__(self, message: str, *, operation: str) -> None:
        super().__init__(message)
        self.operation = operation


class CacheStaleDataError(CacheError):
    """Cache data is stale (version mismatch)."""

    def __init__(self, message: str, *, operation: str) -> None:
        super().__init__(message)
        self.operation = operation


class CacheInvalidDataError(CacheError):
    """Cache data is invalid (malformed JSON)."""

    def __init__(self, message: str, *, operation: str) -> None:
        super().__init__(message)
        self.operation = operation


class UnexpectedCacheError(UnexpectedAppError):
    """Unexpected Redis error, not belonging to explicit classes above."""
