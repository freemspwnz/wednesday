"""Ошибки доступа к кэшу (application), на которые мапятся сбои Redis-адаптера."""

from __future__ import annotations

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


class UnexpectedCacheError(UnexpectedAppError):
    """Unexpected Redis error, not belonging to explicit classes above."""
