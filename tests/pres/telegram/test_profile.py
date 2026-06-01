"""Tests for profile message formatting."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from domain.kernel.vo import AwareDatetime
from domain.user import UserRole
from presentation.aiogram.messages import profile as profile_msg

from .factories import mk_user_context


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 5, 22, hour, 0, tzinfo=UTC))


@pytest.mark.unit
def test_format_me_active_user() -> None:
    text = profile_msg.format_me(mk_user_context())
    assert "Роль: Пользователь" in text
    assert "Подписка: Бесплатная" in text
    assert "Лимит в день: 3" in text
    assert "Перерыв: 3 мин" in text
    assert "Действует до: бессрочно" in text
    assert "Модель: gigachat-2-lite" in text
    assert "Статус: Активен" in text


@pytest.mark.unit
def test_format_me_shows_selected_model() -> None:
    from dom.user.factories import mk_user

    from domain.catalog import Model, Series, Vendor
    from domain.user.vo import UserSettings

    user = mk_user(
        settings=UserSettings(
            vendor=Vendor.parse("sber"),
            series=Series.parse("gigachat"),
            model=Model.parse("gigachat-2-pro"),
        ),
    )
    text = profile_msg.format_me(mk_user_context(user=user))
    assert "Модель: gigachat-2-pro" in text


@pytest.mark.unit
def test_format_me_banned_with_until() -> None:
    from dom.user.factories import mk_user

    entity = mk_user()
    entity.ban(actor=UserRole.OWNER, until=dt(18), at=dt(17))
    text = profile_msg.format_me(mk_user_context(user=entity))
    assert "Статус: Заблокирован до" in text
    assert str(dt(18)) in text


@pytest.mark.unit
def test_format_me_premium_with_expiry() -> None:
    from dom.user.factories import mk_user, subscription_premium

    entity = mk_user(
        role=UserRole.ADMIN,
        now=dt(10),
    )
    entity.change_subscription(
        actor=UserRole.OWNER,
        new_subscription=subscription_premium(dt(10), expires_at=dt(12)),
        at=dt(11),
    )
    text = profile_msg.format_me(mk_user_context(user=entity))
    assert "Роль: Администратор" in text
    assert "Подписка: Премиум" in text
    assert str(dt(12)) in text
