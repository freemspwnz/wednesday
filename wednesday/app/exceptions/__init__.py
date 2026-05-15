"""Модуль ошибок application-слоя."""

from .application import ChatNotFoundError, UserNotFoundError
from .base import AppError, UnexpectedAppError
from .observe import (
    LogMessageFormatError,
    PrometheusExportError,
    PrometheusHttpExporterError,
    PrometheusObserveError,
)
from .persistence import (
    CacheBackendError,
    CacheTimeoutError,
    CacheUnavailableError,
    SQLAAggregateMappingError,
    SQLADataIntegrityError,
    SQLAError,
    SQLARepositoryError,
    UnexpectedCacheError,
    UnexpectedSQLAError,
)
from .resilience import (
    CircuitError,
    CircuitOpenError,
    CircuitStorageError,
    LimitError,
    LimitStorageError,
    MaxAttemptsExhaustedError,
    RetryError,
    TooManyRequests,
    UnexpectedCircuitError,
    UnexpectedLimitError,
    UnexpectedRetryError,
)
from .utils import unwrap_exception

__all__ = [
    "AppError",
    "CacheBackendError",
    "CacheTimeoutError",
    "CacheUnavailableError",
    "ChatNotFoundError",
    "CircuitError",
    "CircuitOpenError",
    "CircuitStorageError",
    "LimitError",
    "LimitStorageError",
    "LogMessageFormatError",
    "MaxAttemptsExhaustedError",
    "PrometheusExportError",
    "PrometheusHttpExporterError",
    "PrometheusObserveError",
    "RetryError",
    "SQLAAggregateMappingError",
    "SQLADataIntegrityError",
    "SQLAError",
    "SQLARepositoryError",
    "TooManyRequests",
    "UnexpectedAppError",
    "UnexpectedCacheError",
    "UnexpectedCircuitError",
    "UnexpectedLimitError",
    "UnexpectedRetryError",
    "UnexpectedSQLAError",
    "UserNotFoundError",
    "unwrap_exception",
]
