"""User-facing /me profile message templates."""

from zoneinfo import ZoneInfo

from app.dto import UserContext
from domain.catalog import SubscriptionTier
from domain.kernel.vo import AwareDatetime
from domain.user import UserRole

_DISPLAY_TZ = ZoneInfo("Europe/Moscow")

_ROLE_LABELS: dict[UserRole, str] = {
    UserRole.USER: "Пользователь",
    UserRole.ADMIN: "Администратор",
    UserRole.OWNER: "Владелец",
    UserRole.SYSTEM: "Система",
}

_TIER_LABELS: dict[SubscriptionTier, str] = {
    SubscriptionTier.FREE: "Бесплатная",
    SubscriptionTier.PREMIUM: "Премиум",
}

_STATUS_ACTIVE = "Активен"
_STATUS_BANNED = "Заблокирован"
_UNLIMITED = "бессрочно"


def format_me(user: UserContext) -> str:
    lines = [
        "👤 Ваш профиль",
        "",
        f"Роль: {_ROLE_LABELS[user.role]}",
        *_subscription_lines(user),
        *_model_lines(user),
        "",
        f"Статус: {_status_line(user)}",
    ]
    return "\n".join(lines)


def _subscription_lines(user: UserContext) -> list[str]:
    lines = [f"Подписка: {_TIER_LABELS[user.subscription_tier]}"]
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


def _format_dt(dt: AwareDatetime) -> str:
    local = dt.value.astimezone(_DISPLAY_TZ)
    return f"{local:%d.%m.%Y}, {local:%H:%M} ({_DISPLAY_TZ.key})"
