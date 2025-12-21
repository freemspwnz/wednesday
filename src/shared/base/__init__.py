"""Базовые классы и исключения для сервисов."""

from shared.base.exceptions import (
    AppError,
    CacheError,
    CircuitBreakerOpen,
    ImageGenerationError,
    MessagingAPIError,
    MessagingError,
    MessagingNetworkError,
    StorageError,
)

__all__ = [
    "AppError",
    "CacheError",
    "CircuitBreakerOpen",
    "ImageGenerationError",
    "MessagingAPIError",
    "MessagingError",
    "MessagingNetworkError",
    "StorageError",
]
