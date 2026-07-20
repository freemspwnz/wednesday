"""Тесты user_message_for_exception."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

import pytest

from app.exceptions import AppError, LimitStorageError
from domain.chat import ChatId
from domain.chat.exceptions import (
    AccessDeniedError as ChatAccessDeniedError,
    ChatNotFoundError,
    ScheduleLimitExceededError,
)
from domain.image.exceptions import ImageNotFoundError
from domain.kernel.exceptions import (
    DomainError,
    InvalidStateTransitionError,
    StaleWriteError,
    ValidationError,
)
from domain.user import UserId
from domain.user.exceptions import (
    AccessDeniedError as UserAccessDeniedError,
    CooldownViolationError,
    LimitViolationError,
    ModelNotFoundError,
    ModelSelectionError,
    UserBannedError,
    UserNotFoundError,
)
from presentation.aiogram.messages.exceptions import (
    IMAGE_NOT_FOUND,
    MODEL_NOT_FOUND,
    user_message_for_exception,
)


def _cases() -> list[tuple[Callable[[], BaseException], str | None]]:
    return [
        (lambda: UserNotFoundError(str(UserId(UUID(int=1)))), "Пользователь не найден."),
        (lambda: ChatNotFoundError(str(ChatId(value=UUID(int=2)))), "Чат не найден."),
        (lambda: LimitStorageError("x"), "Сервис временно перегружен. Попробуйте позже."),
        (lambda: UserBannedError("banned"), "Доступ ограничен."),
        (lambda: UserAccessDeniedError("no"), "Недостаточно прав для этой операции."),
        (lambda: ChatAccessDeniedError("no"), "Недостаточно прав для этой операции."),
        (lambda: LimitViolationError("lim", {}), "Лимит исчерпан. Попробуйте позже."),
        (lambda: CooldownViolationError("cd", {}), "Лимит исчерпан. Попробуйте позже."),
        (lambda: ScheduleLimitExceededError(5), "Достигнут лимит расписаний для чата."),
        (lambda: ImageNotFoundError("img-1"), IMAGE_NOT_FOUND),
        (lambda: ModelNotFoundError("missing-model"), MODEL_NOT_FOUND),
        (lambda: ModelSelectionError("tier_too_low"), "Модель недоступна для вашей подписки."),
        (lambda: ModelSelectionError("model_not_active"), "Эта модель недоступна."),
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
