"""Доменные исключения.

Иерархия:
    DomainError
    ├── ValidationError
    ├── ContentNotFoundError
    ├── AccessDeniedError
    │   ├── BannedUserError
    │   └── BannedChatError
    ├── GenerationLimitExceededError
    ├── UnsafeContentError
    └── InvalidStateTransitionError
"""


class DomainError(Exception):
    """Базовое доменное исключение с человекопонятным сообщением."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


# ── Ошибки данных ──


class ValidationError(DomainError):
    """Данные не соответствуют бизнес-правилам (например, плохой промпт)."""


class ContentNotFoundError(DomainError):
    """Нет подходящего контента (изображения / промпта) под заданные условия."""


# ── Ошибки доступа ──


class AccessDeniedError(DomainError):
    """Доступ запрещён."""


# ── Ошибки ограничений и правил ──


class GenerationLimitExceededError(DomainError):
    """Пользователь исчерпал лимит генераций."""


class UnsafeContentError(DomainError):
    """Контент нарушает правила модерации/безопасности."""


class InvalidStateTransitionError(DomainError):
    """Попытка недопустимого перехода состояния (в GenerationSession)."""
