"""Тесты user_message_for_exception."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest

from app.exceptions import AppError, ChatNotFoundError, LimitStorageError, UserNotFoundError
from domain.chat import ChatId
from domain.chat.exceptions import ManagementAccessDeniedError as ChatDenied, ScheduleLimitExceededError
from domain.kernel.exceptions import (
    AccessDeniedError,
    DomainError,
    InvalidStateTransitionError,
    StaleWriteError,
    ValidationError,
)
from domain.user import UserId
from domain.user.exceptions import (
    CooldownViolationError,
    LimitViolationError,
    ManagementAccessDeniedError as UserDenied,
    UserBannedError,
)
from presentation.aiogram.messages.exceptions import user_message_for_exception


def _cases() -> list[tuple[Callable[[], BaseException], str | None]]:
    return [
        (lambda: UserNotFoundError(UserId(UUID(int=1))), "Пользователь не найден."),
        (lambda: ChatNotFoundError(ChatId(value=UUID(int=2))), "Чат не найден."),
        (lambda: LimitStorageError("x"), "Сервис временно перегружен. Попробуйте позже."),
        (lambda: UserBannedError("banned"), "Доступ ограничен."),
        (lambda: UserDenied("no"), "Недостаточно прав для этой операции."),
        (lambda: ChatDenied("no"), "Недостаточно прав для этой операции."),
        (lambda: AccessDeniedError("no"), "Недостаточно прав для этой операции."),
        (lambda: LimitViolationError("lim", {}), "Лимит исчерпан. Попробуйте позже."),
        (lambda: CooldownViolationError("cd", {}), "Лимит исчерпан. Попробуйте позже."),
        (lambda: ScheduleLimitExceededError(5), "Достигнут лимит расписаний для чата."),
        (lambda: InvalidStateTransitionError("st"), "Операция недоступна в текущем состоянии."),
        (lambda: StaleWriteError("old"), "Данные устарели. Повторите команду."),
        (lambda: ValidationError("bad"), "bad"),
        (lambda: ValueError("Укажите числовой Telegram ID, не username"), "Укажите числовой Telegram ID, не username"),
        (lambda: DomainError("dom"), "dom"),
        (lambda: AppError("app"), "app"),
        (lambda: RuntimeError("x"), None),
    ]


@pytest.mark.unit
@pytest.mark.parametrize(("factory", "expected"), _cases(), ids=[f"case_{i}" for i in range(len(_cases()))])
def test_user_message_for_exception(factory: Callable[[], BaseException], expected: str | None) -> None:
    assert user_message_for_exception(factory()) == expected
