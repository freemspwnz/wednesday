"""Tests for UserManagementUseCase."""

from unittest.mock import AsyncMock

import pytest

from domain.kernel.vo import NonEmptyStr
from domain.user import AccessDeniedError, UserProfile, UserRole
from tests.dom.user.factories import subscription_premium

from .helpers import dt, make_management_uc, mk_user


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_role_happy_path_persists_and_closes_uow() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, uow, cache = make_management_uc(repo=repo)

    got = await uc.change_role(user_id=user.id, actor=UserRole.OWNER, new_role=UserRole.ADMIN, at=dt(11))

    assert got.role == UserRole.ADMIN
    repo.get_by_id.assert_awaited_once_with(user.id)
    repo.save.assert_awaited_once_with(user)
    cache.users.set.assert_awaited_once_with(got)
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_management_access_denied_propagates_and_skips_save() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _uow, cache = make_management_uc(repo=repo)

    with pytest.raises(AccessDeniedError):
        await uc.change_role(user_id=user.id, actor=UserRole.USER, new_role=UserRole.ADMIN, at=dt(11))

    repo.save.assert_not_awaited()
    cache.users.set.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_profile_happy_path() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, _ = make_management_uc(repo=repo)
    new_profile = UserProfile(telegram_id=user.profile.telegram_id, is_bot=False, first_name=NonEmptyStr(" Neo"))

    await uc.change_profile(user_id=user.id, actor=UserRole.SYSTEM, new_profile=new_profile, at=dt(11))

    assert user.profile.first_name == NonEmptyStr(" Neo")
    repo.save.assert_awaited_once_with(user)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_subscription_happy_path() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _, _ = make_management_uc(repo=repo)
    new_sub = subscription_premium(dt(11))

    await uc.change_subscription(
        user_id=user.id,
        actor=UserRole.ADMIN,
        new_subscription=new_sub,
        at=dt(11),
    )

    assert user.subscription.plan.tier == new_sub.plan.tier
    repo.save.assert_awaited_once_with(user)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_role_refreshes_user_cache_snapshot() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _, cache = make_management_uc(repo=repo)

    got = await uc.change_role(
        user_id=user.id,
        actor=UserRole.OWNER,
        new_role=UserRole.ADMIN,
        at=dt(11),
    )

    cache.users.set.assert_awaited_once_with(got)
    assert got.profile.telegram_id == user.profile.telegram_id
    assert got.role == UserRole.ADMIN
