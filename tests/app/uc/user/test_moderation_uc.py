"""Tests for UserModerationUseCase."""

from unittest.mock import AsyncMock

import pytest

from app.dto import UserContext
from domain.user import ActiveState, UserBanned, UserRole
from domain.user.policies import ViolationStats
from tests.dom.user.factories import FakeUserRepo, FakeViolationRepo

from ...factories import mk_logger
from .helpers import dt, make_moderation_uc, mk_user, plain_dt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_ban_and_unban_happy_path() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10), role=UserRole.USER)
    repo.get_by_id.return_value = user
    uc, _, _ = make_moderation_uc(repo=repo)

    await uc.ban(
        user_id=str(user.id),
        actor=int(UserRole.OWNER),
        until=plain_dt(20),
        at=plain_dt(12),
    )
    assert user.state.is_banned_at(dt(15))
    await uc.unban(user_id=str(user.id), actor=int(UserRole.OWNER), at=plain_dt(13))
    assert isinstance(user.state, ActiveState)

    assert repo.save.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_unban_when_active_is_noop() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, cache = make_moderation_uc(repo=repo)

    got = await uc.unban(user_id=str(user.id), actor=int(UserRole.OWNER), at=plain_dt(11))

    assert isinstance(got, UserContext)
    assert isinstance(user.state, ActiveState)
    assert user.updated_at == dt(10)
    assert user.pull_events() == []
    repo.save.assert_awaited_once()
    cache.users.set.assert_awaited_once_with(got)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_ban_refreshes_user_cache_snapshot() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, cache = make_moderation_uc(repo=repo)

    got = await uc.ban(
        user_id=str(user.id),
        actor=int(UserRole.OWNER),
        until=plain_dt(20),
        at=plain_dt(12),
    )

    assert isinstance(got, UserContext)
    cache.users.set.assert_awaited_once_with(got)
    assert got.is_banned is True
    assert got.banned_until == plain_dt(20)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_unban_after_ban_refreshes_cache_twice() -> None:
    repo = AsyncMock()
    user = mk_user(now=dt(10))
    repo.get_by_id.return_value = user
    uc, _, cache = make_moderation_uc(repo=repo)

    await uc.ban(
        user_id=str(user.id),
        actor=int(UserRole.OWNER),
        until=plain_dt(20),
        at=plain_dt(12),
    )
    await uc.unban(user_id=str(user.id), actor=int(UserRole.OWNER), at=plain_dt(13))

    assert cache.users.set.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_assign_ban_records_strike_without_ban_under_threshold() -> None:
    user = mk_user(now=dt(10))
    user_repo = FakeUserRepo.with_users(user)
    violations = FakeViolationRepo(stats=ViolationStats(hour=0, today=0, week=0, total=0))
    log = mk_logger()
    uc, uow, cache = make_moderation_uc(repo=user_repo, violations=violations, logger=log)

    got = await uc.assign_ban(user_id=str(user.id), at=plain_dt(12))

    assert isinstance(got, UserContext)
    assert got.is_banned is False
    assert isinstance(user.state, ActiveState)
    assert violations.stats.total == 1
    assert uow.enter_count == uow.exit_count == 1
    cache.users.set.assert_awaited_once_with(got)
    log.info.assert_called_once_with(
        "Moderation strike recorded, no ban assigned",
        user_id=str(user.id.value),
        violations_total=1,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_assign_ban_bans_when_threshold_reached() -> None:
    user = mk_user(now=dt(10))
    user_repo = FakeUserRepo.with_users(user)
    violations = FakeViolationRepo(stats=ViolationStats(hour=1, today=1, week=1, total=1))
    log = mk_logger()
    uc, _, cache = make_moderation_uc(repo=user_repo, violations=violations, logger=log)

    got = await uc.assign_ban(user_id=str(user.id), at=plain_dt(12))

    assert isinstance(got, UserContext)
    assert got.is_banned is True
    assert isinstance(user.pull_events()[0], UserBanned)
    assert user.state.is_banned_at(dt(12))
    assert violations.stats.total == 2
    cache.users.set.assert_awaited_once_with(got)
    log.info.assert_called_once()
    assert log.info.call_args.args[0] == "User banned by moderation policy"
    assert log.info.call_args.kwargs["user_id"] == str(user.id.value)
    assert log.info.call_args.kwargs["violations_total"] == 2
