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


class UnexpectedAppError(AppError):
    """Базовый класс для неожиданных ошибок application‑слоя.

    Используется для обёртки действительно неожиданных ошибок (программные баги,
    нарушения инвариантов), которые не относятся к ожидаемым доменным или
    инфраструктурным сбоям.
    """

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.original_error = original_error


class UnexpectedDispatchError(UnexpectedAppError):
    """Неожиданная ошибка при выполнении рассылки или отправке сообщений."""

    pass


class UnexpectedImageError(UnexpectedAppError):
    """Неожиданная ошибка при генерации или сохранении изображений."""

    pass


class UnexpectedPromptError(UnexpectedAppError):
    """Неожиданная ошибка при генерации или получении fallback‑промпта."""

    pass


class UnexpectedAPIError(UnexpectedAppError):
    """Неожиданная ошибка при работе с внешними API статуса/списков моделей."""

    pass


class ClientError(AppError):
    """Базовое исключение для всех ошибок клиентов API."""

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        """Инициализирует исключение клиента.

        Args:
            message: Сообщение об ошибке.
            original_error: Исходное исключение, которое привело к этой ошибке (опционально).
        """
        super().__init__(message)
        self.message = message
        self.original_error = original_error


class AuthenticationError(ClientError):
    """Ошибка аутентификации (401 Unauthorized, 403 Forbidden)."""

    pass


class RateLimitError(ClientError):
    """Превышен лимит запросов (429 Too Many Requests)."""

    pass


class NetworkError(ClientError):
    """Сетевая ошибка (таймаут, ошибка соединения, DNS и т.д.)."""

    pass


class APIError(ClientError):
    """Ошибка API (другие HTTP статусы: 4xx, 5xx)."""

    pass
