"""Модуль ошибок application-слоя."""

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
    "unwrap_exception",
]
