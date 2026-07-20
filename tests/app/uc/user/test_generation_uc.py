"""Tests for UserGenerationUseCase access/usage methods."""

from uuid import UUID

import pytest

from domain.user import (
    LimitViolationError,
    UserBannedError,
    UserId,
    UserNotFoundError,
    UserRole,
)
from domain.user.policies import UsageStats
from tests.dom.user.factories import FakeUsageRepo, FakeUserRepo

from .helpers import dt, make_generation_uc, mk_user


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_assert_allowed_does_not_record_usage() -> None:
    user = mk_user(now=dt(10))
    users = FakeUserRepo.with_users(user)
    usage = FakeUsageRepo(stats=UsageStats(last_usage=dt(1), daily_usage=0))
    uc, uow, _ = make_generation_uc(repo=users, usage=usage)

    await uc.assert_allowed(user_id=user.id, at=dt(12))

    assert usage.stats.daily_usage == 0
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_assert_allowed_propagates_ban_and_limit() -> None:
    user = mk_user(now=dt(10))
    user.ban(actor=UserRole.OWNER, until=dt(20), at=dt(11))
    users = FakeUserRepo.with_users(user)
    uc, _, _ = make_generation_uc(repo=users)

    with pytest.raises(UserBannedError):
        await uc.assert_allowed(user_id=user.id, at=dt(12))

    user.unban(actor=UserRole.OWNER, at=dt(12))
    usage = FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=100))
    uc, _, _ = make_generation_uc(repo=users, usage=usage)
    with pytest.raises(LimitViolationError):
        await uc.assert_allowed(user_id=user.id, at=dt(13))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_record_usage_consumes_slot() -> None:
    usage = FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=0))
    uc, uow, _ = make_generation_uc(repo=FakeUserRepo(), usage=usage)

    await uc.record_usage(user_id=UserId(UUID(int=1)), at=dt(12))

    assert usage.stats.daily_usage == 1
    assert usage.stats.last_usage == dt(12)
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_assert_allowed_propagates_not_found() -> None:
    uc, _, _ = make_generation_uc(repo=FakeUserRepo())

    with pytest.raises(UserNotFoundError):
        await uc.assert_allowed(user_id=UserId(UUID(int=404)), at=dt(12))
