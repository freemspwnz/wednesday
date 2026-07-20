"""Tests for UserModerationUseCase."""

from unittest.mock import AsyncMock

import pytest

from domain.user import ActiveState, UserRole
from domain.user.exceptions import InvalidStateTransitionError

from .helpers import dt, make_moderation_uc, mk_user


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_ban_and_unban_happy_path() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _, _ = make_moderation_uc(repo=repo)

    await uc.ban(user_id=user.id, actor=UserRole.OWNER, until=dt(20), at=dt(12))
    assert user.state.is_banned_at(dt(15))
    await uc.unban(user_id=user.id, actor=UserRole.OWNER, at=dt(13))
    assert isinstance(user.state, ActiveState)

    assert repo.save.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_unban_active_propagates_invalid_transition() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, cache = make_moderation_uc(repo=repo)

    with pytest.raises(InvalidStateTransitionError):
        await uc.unban(user_id=user.id, actor=UserRole.OWNER, at=dt(11))
    cache.users.set.assert_not_awaited()
    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_ban_refreshes_user_cache_snapshot() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, cache = make_moderation_uc(repo=repo)

    got = await uc.ban(user_id=user.id, actor=UserRole.OWNER, until=dt(20), at=dt(12))

    cache.users.set.assert_awaited_once_with(got)
    assert got.state.is_banned_at(dt(15))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_unban_after_ban_refreshes_cache_twice() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, cache = make_moderation_uc(repo=repo)

    await uc.ban(user_id=user.id, actor=UserRole.OWNER, until=dt(20), at=dt(12))
    await uc.unban(user_id=user.id, actor=UserRole.OWNER, at=dt(13))

    assert cache.users.set.await_count == 2
