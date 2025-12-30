"""Базовые классы и исключения для сервисов."""

from shared.base.exceptions import (
    AppError,
    CacheError,
    CircuitBreakerOpen,
    ImageGenerationError,
    MessagingAPIError,
    MessagingError,
    MessagingFeatureNotSupported,
    MessagingNetworkError,
    StorageError,
    UnexpectedImageGenerationError,
)

__all__ = [
    "AppError",
    "CacheError",
    "CircuitBreakerOpen",
    "ImageGenerationError",
    "MessagingAPIError",
    "MessagingError",
    "MessagingFeatureNotSupported",
    "MessagingNetworkError",
    "StorageError",
    "UnexpectedImageGenerationError",
]
