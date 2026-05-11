"""Модуль ошибок application-слоя."""

from .application import ChatNotFoundError, UserNotFoundError
from .base import AppError, UnexpectedAppError
from .persistence import (
    SQLAAggregateMappingError,
    SQLADataIntegrityError,
    SQLAError,
    SQLARepositoryError,
    UnexpectedSQLAError,
)
from .resilience import (
    CircuitOpenError,
    CircuitStateChangeError,
    RateLimitError,
    RetryError,
    TooManyRequests,
    UnexpectedCircuitError,
    UnexpectedRateLimitError,
    UnexpectedRetryError,
)
from .utils import unwrap_exception

__all__ = [
    "AppError",
    "ChatNotFoundError",
    "CircuitOpenError",
    "CircuitStateChangeError",
    "RateLimitError",
    "RetryError",
    "SQLAAggregateMappingError",
    "SQLADataIntegrityError",
    "SQLAError",
    "SQLARepositoryError",
    "TooManyRequests",
    "UnexpectedAppError",
    "UnexpectedCircuitError",
    "UnexpectedRateLimitError",
    "UnexpectedRetryError",
    "UnexpectedSQLAError",
    "UserNotFoundError",
    "unwrap_exception",
]
