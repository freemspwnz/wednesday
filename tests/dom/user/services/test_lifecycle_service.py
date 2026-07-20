"""Tests for UserLifecycleService."""

from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import (
    User,
    UserId,
    UserLifecycleService,
    UserNotFoundError,
    UserProfile,
    UserRole,
)
from domain.user.services.utils import user_id_from_tg
from tests.dom.user.factories import FakeModelCatalog, FakeSubscriptionCatalog, default_settings, dt, subscription_free


def mk_user(*, user_id: int = 1, role: UserRole = UserRole.USER, now: AwareDatetime | None = None) -> User:
    current = now or dt(12)
    return User.register(
        id=UserId(UUID(int=user_id)),
        profile=UserProfile(telegram_id=100_000 + user_id, is_bot=False, first_name=NonEmptyStr("Test")),
        role=role,
        subscription=subscription_free(current),
        settings=default_settings(),
        at=current,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_or_create_returns_existing_and_updates_seen() -> None:
    repo = AsyncMock()
    existing = mk_user(now=dt(10))
    repo.get_by_id.return_value = existing

    result = await UserLifecycleService.get_or_create(
        profile=UserProfile(telegram_id=existing.profile.telegram_id, is_bot=False, first_name=NonEmptyStr("Test")),
        repo=repo,
        models=FakeModelCatalog(),
        subscriptions=FakeSubscriptionCatalog(),
        at=dt(11),
    )

    assert result is existing
    repo.get_by_id.assert_awaited_once()
    repo.save.assert_awaited_once_with(existing)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_or_create_creates_new_entity() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    profile = UserProfile(
        telegram_id=111,
        is_bot=False,
        first_name=NonEmptyStr("John"),
        has_tg_premium=True,
    )

    result = await UserLifecycleService.get_or_create(
        profile=profile,
        repo=repo,
        models=FakeModelCatalog(),
        subscriptions=FakeSubscriptionCatalog(),
        at=dt(9),
    )

    assert isinstance(result, User)
    assert result.profile.telegram_id == 111
    assert result.role == UserRole.USER
    assert result.profile.has_tg_premium is True
    assert str(result.settings.model) == "gigachat-2-lite"
    repo.save.assert_awaited_once_with(result)


@pytest.mark.unit
def test_user_id_from_tg_is_deterministic() -> None:
    assert user_id_from_tg(1) == user_id_from_tg(1)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_mark_seen_raises_not_found() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    uid = UserId(UUID(int=99))

    with pytest.raises(UserNotFoundError) as ei:
        await UserLifecycleService.mark_seen(id=uid, repo=repo, at=dt(12))

    assert ei.value.user_id == str(uid)
    repo.save.assert_not_awaited()
