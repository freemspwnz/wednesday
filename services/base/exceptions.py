"""Кастомные исключения для сервисов."""

from __future__ import annotations


class ServiceException(Exception):
    """Базовое исключение для всех ошибок сервисов."""

    pass


class ImageGenerationError(ServiceException):
    """Ошибка при генерации изображения."""

    pass


class CacheError(ServiceException):
    """Ошибка при работе с кэшем."""

    pass


class RateLimitExceeded(ServiceException):
    """Превышен лимит частоты запросов."""

    pass


class CircuitBreakerOpen(ServiceException):
    """Circuit breaker открыт, запросы заблокированы."""

    pass


class PromptGenerationError(ServiceException):
    """Ошибка при генерации промпта."""

    pass


class StorageError(ServiceException):
    """Ошибка при работе с хранилищем данных."""

    pass
