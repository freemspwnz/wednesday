"""Tests for user_message_for_exception."""

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
from domain.image.exceptions import GenerationError, ImageNotFoundError, PromptRejectedError
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
    GENERATION_FAILED,
    IMAGE_NOT_FOUND,
    LIMIT_EXHAUSTED,
    MODEL_NOT_FOUND,
    PROMPT_REJECTED,
    WAIT_FOR_COOLDOWN,
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
        (lambda: LimitViolationError("lim", {}), LIMIT_EXHAUSTED),
        (
            lambda: CooldownViolationError("cd", {"remaining_seconds": 90, "cooldown_minutes": 3}),
            WAIT_FOR_COOLDOWN.format(minutes=1, seconds=30),
        ),
        (
            lambda: CooldownViolationError("cd", {}),
            WAIT_FOR_COOLDOWN.format(minutes=1, seconds=0),
        ),
        (lambda: ScheduleLimitExceededError(5), "Достигнут лимит расписаний для чата."),
        (lambda: PromptRejectedError("prohibited_content"), PROMPT_REJECTED),
        (lambda: GenerationError("boom"), GENERATION_FAILED),
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
