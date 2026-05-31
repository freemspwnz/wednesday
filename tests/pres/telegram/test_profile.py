"""Tests for profile message formatting."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.dto import UserContext
from domain.catalog import SubscriptionTier
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import UserRole
from presentation.aiogram.messages import profile as profile_msg


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 5, 22, hour, 0, tzinfo=UTC))


def _user(**kwargs: object) -> UserContext:
    defaults: dict[str, object] = {
        "tg_id": 1,
        "is_bot": False,
        "first_name": NonEmptyStr("A"),
        "role": UserRole.USER,
        "subscription_tier": SubscriptionTier.FREE,
        "subscription_daily_limit": 3,
        "subscription_cooldown_minutes": 5,
    }
    defaults.update(kwargs)
    return UserContext(**defaults)  # type: ignore[arg-type]


@pytest.mark.unit
def test_format_me_role_unknown() -> None:
    text = profile_msg.format_me(_user(role=None))
    assert text == profile_msg.ROLE_UNKNOWN


@pytest.mark.unit
def test_format_me_active_user() -> None:
    text = profile_msg.format_me(_user())
    assert "Роль: Пользователь" in text
    assert "Подписка: Бесплатная" in text
    assert "Лимит в день: 3" in text
    assert "Перерыв: 5 мин" in text
    assert "Действует до: бессрочно" in text
    assert "Модель: не выбрана" in text
    assert "Статус: Активен" in text


@pytest.mark.unit
def test_format_me_shows_selected_model() -> None:
    text = profile_msg.format_me(_user(model="gigachat-2-pro"))
    assert "Модель: gigachat-2-pro" in text


@pytest.mark.unit
def test_format_me_banned_with_until() -> None:
    text = profile_msg.format_me(
        _user(
            is_banned=True,
            is_active=False,
            banned_until=dt(18),
        ),
    )
    assert "Статус: Заблокирован до" in text
    assert str(dt(18)) in text


@pytest.mark.unit
def test_format_me_premium_with_expiry() -> None:
    text = profile_msg.format_me(
        _user(
            role=UserRole.ADMIN,
            subscription_tier=SubscriptionTier.PREMIUM,
            subscription_daily_limit=10,
            subscription_cooldown_minutes=1,
            subscription_expires_at=dt(12),
        ),
    )
    assert "Роль: Администратор" in text
    assert "Подписка: Премиум" in text
    assert str(dt(12)) in text
