"""Статические тексты ошибок, fallback-сообщения и маппинг исключений → UX."""

from __future__ import annotations

from builtins import BaseException

from app.exceptions import AppError, ChatNotFoundError, LimitStorageError, UserNotFoundError
from domain.chat.exceptions import (
    ManagementAccessDeniedError as ChatManagementAccessDeniedError,
    ScheduleLimitExceededError,
)
from domain.kernel.exceptions import (
    AccessDeniedError,
    DomainError,
    InvalidStateTransitionError,
    StaleWriteError,
    ValidationError,
)
from domain.user.exceptions import (
    CooldownViolationError,
    LimitViolationError,
    ManagementAccessDeniedError as UserManagementAccessDeniedError,
    UserBannedError,
)

SERVER_ERROR = "⚠️ Произошла ошибка на сервере. Мы уже в курсе и чиним!"

COMMAND_FAILURE = "Не удалось выполнить команду."

USER_NOT_FOUND = "Пользователь не найден."

CHAT_NOT_FOUND = "Чат не найден."

LIMIT_STORAGE_BUSY = "Сервис временно перегружен. Попробуйте позже."

ACCESS_RESTRICTED = "Доступ ограничен."

INSUFFICIENT_PERMISSIONS = "Недостаточно прав для этой операции."

LIMIT_EXHAUSTED = "Лимит исчерпан. Попробуйте позже."

SCHEDULE_LIMIT_EXCEEDED = "Достигнут лимит расписаний для чата."

INVALID_STATE = "Операция недоступна в текущем состоянии."

STALE_WRITE = "Данные устарели. Повторите команду."


def user_message_for_exception(exc: BaseException) -> str | None:
    """User-facing text; None means use a generic fallback message."""
    if isinstance(exc, UserNotFoundError):
        return USER_NOT_FOUND
    if isinstance(exc, ChatNotFoundError):
        return CHAT_NOT_FOUND
    if isinstance(exc, LimitStorageError):
        return LIMIT_STORAGE_BUSY
    if isinstance(exc, UserBannedError):
        return ACCESS_RESTRICTED
    if isinstance(
        exc,
        UserManagementAccessDeniedError | ChatManagementAccessDeniedError | AccessDeniedError,
    ):
        return INSUFFICIENT_PERMISSIONS
    if isinstance(exc, LimitViolationError | CooldownViolationError):
        return LIMIT_EXHAUSTED
    if isinstance(exc, ScheduleLimitExceededError):
        return SCHEDULE_LIMIT_EXCEEDED
    if isinstance(exc, InvalidStateTransitionError):
        return INVALID_STATE
    if isinstance(exc, StaleWriteError):
        return STALE_WRITE
    if isinstance(exc, ValidationError):
        return exc.message
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, DomainError):
        return exc.message
    if isinstance(exc, AppError):
        return str(exc)
    return None
