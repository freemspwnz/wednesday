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
    "CacheBackendError",
    "CacheTimeoutError",
    "CacheUnavailableError",
    "ChatNotFoundError",
    "CircuitOpenError",
    "CircuitStateChangeError",
    "LogMessageFormatError",
    "PrometheusExportError",
    "PrometheusHttpExporterError",
    "PrometheusObserveError",
    "RateLimitError",
    "RetryError",
    "SQLAAggregateMappingError",
    "SQLADataIntegrityError",
    "SQLAError",
    "SQLARepositoryError",
    "TooManyRequests",
    "UnexpectedAppError",
    "UnexpectedCacheError",
    "UnexpectedCircuitError",
    "UnexpectedRateLimitError",
    "UnexpectedRetryError",
    "UnexpectedSQLAError",
    "UserNotFoundError",
    "unwrap_exception",
]
