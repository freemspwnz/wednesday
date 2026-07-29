"""Tests for profile message formatting."""

import pytest

from domain.catalog import Model, Series, Vendor
from domain.user import UserRole
from domain.user.vo import UserSettings
from presentation.aiogram.messages import user as user_msg
from tests.dom.user.factories import mk_user, subscription_premium

from ..factories import dt, mk_user_context


@pytest.mark.unit
def test_format_me_active_user() -> None:
    text = user_msg.format_me(mk_user_context())
    assert "Роль: Пользователь" in text
    assert "Подписка: Бесплатная" in text
    assert "Лимит в день: 3" in text
    assert "Перерыв: 3 мин" in text
    assert "Действует до: бессрочно" in text
    assert "Модель: gigachat-2-lite" in text
    assert "Статус: Активен" in text


@pytest.mark.unit
def test_format_me_shows_selected_model() -> None:
    user = mk_user(
        settings=UserSettings(
            vendor=Vendor.parse("sber"),
            series=Series.parse("gigachat"),
            model=Model.parse("gigachat-2-pro"),
        ),
    )
    text = user_msg.format_me(mk_user_context(user=user))
    assert "Модель: gigachat-2-pro" in text


@pytest.mark.unit
def test_format_me_banned_with_until() -> None:
    entity = mk_user()
    entity.ban(actor=UserRole.OWNER, until=dt(18), at=dt(17))
    text = user_msg.format_me(mk_user_context(user=entity))
    assert "Статус: Заблокирован до" in text
    assert "22.05.2026, 21:00 (Europe/Moscow)" in text


@pytest.mark.unit
def test_format_me_banned_without_until() -> None:
    ctx = mk_user_context()
    ctx.is_banned = True
    ctx.banned_until = None
    text = user_msg.format_me(ctx)
    assert "Статус: Заблокирован" in text
    assert "до" not in text.split("Статус:")[1]


@pytest.mark.unit
def test_format_me_premium_with_expiry() -> None:
    entity = mk_user(
        role=UserRole.ADMIN,
        now=dt(10),
    )
    entity.change_subscription(
        actor=UserRole.OWNER,
        new_subscription=subscription_premium(dt(10), expires_at=dt(12)),
        at=dt(11),
    )
    text = user_msg.format_me(mk_user_context(user=entity))
    assert "Роль: Администратор" in text
    assert "Подписка: Премиум" in text
    assert "22.05.2026, 15:00 (Europe/Moscow)" in text
