"""User-facing profile and model command texts."""

from collections.abc import Sequence
from datetime import datetime
from zoneinfo import ZoneInfo

from app.dto import UserContext

_DISPLAY_TZ = ZoneInfo("Europe/Moscow")

_STATUS_ACTIVE = "Активен"
_STATUS_BANNED = "Заблокирован"
_UNLIMITED = "бессрочно"

SET_MODEL_USAGE = "Использование: /set_model <модель>"

LIST_MODELS_EMPTY = "Нет доступных моделей для вашей подписки."

LIST_MODELS_HEADER = "Доступные модели:"

LIST_MODELS_FOOTER = "Выбор: /set_model <код модели>"


def format_me(user: UserContext) -> str:
    lines = [
        "👤 Ваш профиль",
        "",
        f"Роль: {user.role_label}",
        *_subscription_lines(user),
        *_model_lines(user),
        "",
        f"Статус: {_status_line(user)}",
    ]
    return "\n".join(lines)


def _subscription_lines(user: UserContext) -> list[str]:
    lines = [f"Подписка: {user.subscription_label}"]
    lines.append(f"Лимит в день: {user.subscription_daily_limit}")
    lines.append(f"Перерыв: {user.subscription_cooldown_minutes} мин")
    if user.subscription_expires_at is not None:
        lines.append(f"Действует до: {_format_dt(user.subscription_expires_at)}")
    else:
        lines.append(f"Действует до: {_UNLIMITED}")
    return lines


def _model_lines(user: UserContext) -> list[str]:
    return [f"Модель: {user.model}"]


def _status_line(user: UserContext) -> str:
    if user.is_banned:
        if user.banned_until is not None:
            return f"{_STATUS_BANNED} до {_format_dt(user.banned_until)}"
        return _STATUS_BANNED
    return _STATUS_ACTIVE


def _format_dt(dt: datetime) -> str:
    local = dt.astimezone(_DISPLAY_TZ)
    return f"{local:%d.%m.%Y}, {local:%H:%M} ({_DISPLAY_TZ.key})"


def format_set_model_success(model: str) -> str:
    return f"✅ Модель изменена: {model}"


def format_list_models(models: Sequence[str]) -> str:
    if not models:
        return LIST_MODELS_EMPTY
    lines = [LIST_MODELS_HEADER, "", *(f"• {model}" for model in models), "", LIST_MODELS_FOOTER]
    return "\n".join(lines)
