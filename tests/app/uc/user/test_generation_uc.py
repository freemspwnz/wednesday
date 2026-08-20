"""Tests for UserGenerationUseCase access/usage methods."""

import asyncio
from uuid import UUID

import pytest

from app.use_cases.user import UserGenerationUseCase
from domain.user import (
    CooldownViolationError,
    LimitViolationError,
    UsageStats,
    UserBannedError,
    UserId,
    UserNotFoundError,
    UserRole,
)
from tests.app.factories import FakeCacheRegistry, FakeUoW, mk_logger
from tests.dom.user.factories import (
    FakeModelCatalog,
    FakeSubscriptionCatalog,
    FakeUsageRepo,
    FakeUserRepo,
)

from .helpers import dt, make_generation_uc, mk_user, plain_dt


def _make_generation_uc_for_request(
    *,
    users: FakeUserRepo,
    usage: FakeUsageRepo,
    cache: FakeCacheRegistry,
) -> UserGenerationUseCase:
    uow = FakeUoW(users=users, usage=usage)
    return UserGenerationUseCase(
        uow=uow,
        cache=cache.users,
        models=FakeModelCatalog(),
        subscriptions=FakeSubscriptionCatalog(),
        logger=mk_logger(),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_concurrent_begin_generation_rejects_second_request() -> None:
    user = mk_user(now=dt(10))
    users = FakeUserRepo.with_users(user)
    usage = FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=0))
    cache = FakeCacheRegistry()

    async def attempt() -> object:
        uc = _make_generation_uc_for_request(users=users, usage=usage, cache=cache)
        return await uc.begin_generation(user_id=str(user.id), at=plain_dt(12))

    first, second = await asyncio.gather(attempt(), attempt(), return_exceptions=True)

    outcomes = [first, second]
    successes = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
    cooldown_violations = [outcome for outcome in outcomes if isinstance(outcome, CooldownViolationError)]

    assert len(successes) == 1
    assert len(cooldown_violations) == 1
    assert usage.stats.daily_usage == 1
    assert usage.stats.last_usage == dt(12)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_begin_generation_then_second_call_hits_cooldown() -> None:
    user = mk_user(now=dt(10))
    users = FakeUserRepo.with_users(user)
    usage = FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=0))
    uc, _, _ = make_generation_uc(repo=users, usage=usage)

    await uc.begin_generation(user_id=str(user.id), at=plain_dt(12))

    with pytest.raises(CooldownViolationError):
        await uc.begin_generation(user_id=str(user.id), at=plain_dt(12))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_refund_generation_restores_previous_state() -> None:
    user = mk_user(now=dt(10))
    users = FakeUserRepo.with_users(user)
    usage = FakeUsageRepo(stats=UsageStats(last_usage=dt(9), daily_usage=1))
    uc, _, _ = make_generation_uc(repo=users, usage=usage)

    snap = await uc.begin_generation(user_id=str(user.id), at=plain_dt(12))
    await uc.refund_generation(user_id=str(user.id), snapshot=snap)

    assert usage.stats.last_usage == dt(9)
    assert usage.stats.daily_usage == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_begin_generation_propagates_ban_and_limit() -> None:
    user = mk_user(now=dt(10))
    user.ban(actor=UserRole.OWNER, until=dt(20), at=dt(11))
    users = FakeUserRepo.with_users(user)
    uc, _, _ = make_generation_uc(repo=users)

    with pytest.raises(UserBannedError):
        await uc.begin_generation(user_id=str(user.id), at=plain_dt(12))

    user.unban(actor=UserRole.OWNER, at=dt(12))
    usage = FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=100))
    uc, _, _ = make_generation_uc(repo=users, usage=usage)

    with pytest.raises(LimitViolationError):
        await uc.begin_generation(user_id=str(user.id), at=plain_dt(13))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_begin_generation_propagates_not_found() -> None:
    uc, _, _ = make_generation_uc(repo=FakeUserRepo())

    with pytest.raises(UserNotFoundError):
        await uc.begin_generation(user_id=str(UserId(UUID(int=404))), at=plain_dt(12))
