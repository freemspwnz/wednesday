"""Tests for UserManagementUseCase."""

from unittest.mock import AsyncMock

import pytest

from app.dto import UserContext
from domain.user import AccessDeniedError, UserRole

from .helpers import dt, make_management_uc, mk_user, plain_dt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_role_happy_path_persists_and_closes_uow() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, uow, cache = make_management_uc(repo=repo)

    got = await uc.change_role(
        user_id=str(user.id),
        actor=int(UserRole.OWNER),
        action="promote",
        at=plain_dt(11),
    )

    assert isinstance(got, UserContext)
    assert got.role == int(UserRole.ADMIN)
    assert user.role == UserRole.ADMIN
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
        await uc.change_role(
            user_id=str(user.id),
            actor=int(UserRole.USER),
            action="promote",
            at=plain_dt(11),
        )

    repo.save.assert_not_awaited()
    cache.users.set.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_role_demote_happy_path() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.ADMIN)
    repo.get_by_id.return_value = user
    uc, _, cache = make_management_uc(repo=repo)

    got = await uc.change_role(
        user_id=str(user.id),
        actor=int(UserRole.OWNER),
        action="demote",
        at=plain_dt(11),
    )

    assert got.role == int(UserRole.USER)
    assert user.role == UserRole.USER
    cache.users.set.assert_awaited_once_with(got)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_role_refreshes_user_cache_snapshot() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _, cache = make_management_uc(repo=repo)

    got = await uc.change_role(
        user_id=str(user.id),
        actor=int(UserRole.OWNER),
        action="promote",
        at=plain_dt(11),
    )

    cache.users.set.assert_awaited_once_with(got)
    assert got.tg_id == user.profile.telegram_id
    assert got.role == int(UserRole.ADMIN)
