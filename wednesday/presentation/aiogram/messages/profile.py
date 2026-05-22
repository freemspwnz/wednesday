"""Тексты профиля пользователя (/me)."""

from __future__ import annotations

from app.dto import UserContext
from domain.kernel.vo import AwareDatetime
from domain.user import SubscriptionTier, UserRole

ROLE_UNKNOWN = "Не удалось определить вашу роль. Попробуйте позже или обратитесь к администратору."

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
_SUBSCRIPTION_UNKNOWN = "не определена"
_UNLIMITED = "бессрочно"


def format_me(user: UserContext) -> str:
    if user.role is None:
        return ROLE_UNKNOWN

    lines = [
        "👤 Ваш профиль",
        "",
        f"Роль: {_ROLE_LABELS[user.role]}",
        *_subscription_lines(user),
        "",
        f"Статус: {_status_line(user)}",
    ]
    return "\n".join(lines)


def _subscription_lines(user: UserContext) -> list[str]:
    tier = user.subscription_tier
    if tier is None:
        return [f"Подписка: {_SUBSCRIPTION_UNKNOWN}"]

    lines = [f"Подписка: {_TIER_LABELS[tier]}"]
    if user.subscription_daily_limit is not None:
        lines.append(f"Лимит в день: {user.subscription_daily_limit}")
    if user.subscription_cooldown_minutes is not None:
        lines.append(f"Перерыв: {user.subscription_cooldown_minutes} мин")
    if user.subscription_expires_at is not None:
        lines.append(f"Действует до: {_format_dt(user.subscription_expires_at)}")
    else:
        lines.append(f"Действует до: {_UNLIMITED}")
    return lines


def _status_line(user: UserContext) -> str:
    if user.is_banned:
        if user.banned_until is not None:
            return f"{_STATUS_BANNED} до {_format_dt(user.banned_until)}"
        return _STATUS_BANNED
    return _STATUS_ACTIVE


def _format_dt(dt: AwareDatetime) -> str:
    return str(dt)
