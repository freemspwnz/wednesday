"""Static error messages, fallback messages, and mapping exceptions to UX."""

from builtins import BaseException

from app.exceptions import AppError, LimitStorageError
from domain.chat.exceptions import (
    AccessDeniedError as ChatAccessDeniedError,
    ChatNotFoundError,
    ScheduleLimitExceededError,
)
from domain.image.exceptions import (
    GenerationError,
    ImageNotFoundError,
    PromptRejectedError,
)
from domain.kernel.exceptions import (
    DomainError,
    InvalidStateTransitionError,
    StaleWriteError,
    ValidationError,
)
from domain.user.exceptions import (
    AccessDeniedError as UserAccessDeniedError,
    CooldownViolationError,
    LimitViolationError,
    ModelNotFoundError,
    ModelSelectionError,
    UserBannedError,
    UserNotFoundError,
)

SERVER_ERROR = "⚠️ Произошла ошибка на сервере. Мы уже в курсе и чиним!"

COMMAND_FAILURE = "Не удалось выполнить команду."

USER_NOT_FOUND = "Пользователь не найден."

CHAT_NOT_FOUND = "Чат не найден."

LIMIT_STORAGE_BUSY = "Сервис временно перегружен. Попробуйте позже."

ACCESS_RESTRICTED = "Доступ ограничен."

INSUFFICIENT_PERMISSIONS = "Недостаточно прав для этой операции."

LIMIT_EXHAUSTED = "Лимит исчерпан. Приходите завтра."

WAIT_FOR_COOLDOWN = "Подождите ещё {minutes} мин. {seconds} сек. перед новой попыткой."

SCHEDULE_LIMIT_EXCEEDED = "Достигнут лимит расписаний для чата."

INVALID_STATE = "Операция недоступна в текущем состоянии."

STALE_WRITE = "Данные устарели. Повторите команду."

IMAGE_NOT_FOUND = "Изображение не найдено."

MODEL_NOT_FOUND = "Модель не найдена."

PROMPT_REJECTED = "Промпт отклонён модерацией."

GENERATION_FAILED = "Не удалось сгенерировать изображение. Попробуйте позже."

_MODEL_SELECTION_MESSAGES: dict[str, str] = {
    "model_not_active": "Эта модель недоступна.",
    "tier_too_low": "Модель недоступна для вашей подписки.",
}


def _cooldown_message(exc: CooldownViolationError) -> str:
    remaining = exc.details.get("remaining_seconds")
    if isinstance(remaining, int) and remaining > 0:
        total_seconds = remaining
    else:
        cooldown = exc.details.get("cooldown_minutes")
        minutes = cooldown if isinstance(cooldown, int) and cooldown > 0 else 1
        total_seconds = minutes * 60
    minutes, seconds = divmod(total_seconds, 60)
    return WAIT_FOR_COOLDOWN.format(minutes=minutes, seconds=seconds)


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
    if isinstance(exc, UserAccessDeniedError | ChatAccessDeniedError):
        return INSUFFICIENT_PERMISSIONS
    if isinstance(exc, LimitViolationError):
        return LIMIT_EXHAUSTED
    if isinstance(exc, CooldownViolationError):
        return _cooldown_message(exc)
    if isinstance(exc, ScheduleLimitExceededError):
        return SCHEDULE_LIMIT_EXCEEDED
    if isinstance(exc, PromptRejectedError):
        return PROMPT_REJECTED
    if isinstance(exc, GenerationError):
        return GENERATION_FAILED
    if isinstance(exc, ImageNotFoundError):
        return IMAGE_NOT_FOUND
    if isinstance(exc, ModelNotFoundError):
        return MODEL_NOT_FOUND
    if isinstance(exc, ModelSelectionError):
        return _MODEL_SELECTION_MESSAGES.get(exc.code, exc.message)
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
