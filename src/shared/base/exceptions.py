"""Доменные исключения для приложения."""


class AppError(Exception):
    """Базовый класс для всех ошибок приложения."""

    pass


class MessagingError(AppError):
    """Общий класс для ошибок мессенджеров."""

    pass


class MessagingNetworkError(MessagingError):
    """Ошибки сети (таймауты, коннект)."""

    pass


class MessagingAPIError(MessagingError):
    """Ошибки самого API (токен, права, chat_not_found)."""

    pass


class ImageGenerationError(AppError):
    """Ошибки генерации изображений."""

    pass


class StorageError(AppError):
    """Ошибки файлового хранилища."""

    pass


class CacheError(AppError):
    """Ошибки кэширования."""

    pass


class CircuitBreakerOpen(AppError):
    """Ошибка открытого circuit breaker."""

    pass


class RepoError(AppError):
    """Ошибки репозиториев (доступ к БД, операции с данными)."""

    pass


class ServiceError(AppError):
    """Ошибки сервисов (бизнес-логика, координация)."""

    pass
