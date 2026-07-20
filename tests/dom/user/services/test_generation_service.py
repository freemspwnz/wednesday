from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import pytest

from domain.user import (
    BannedState,
    CooldownViolationError,
    LimitViolationError,
    UserBannedError,
    UserGenerationService,
    UserId,
    UserNotFoundError,
    UserRole,
)
from domain.user.exceptions import ValidationError
from domain.user.policies import UsageStats
from domain.user.vo import UserSubscription

from ..factories import (
    FREE_PLAN,
    FakeSubscriptionCatalog,
    FakeUsageRepo,
    FakeUserRepo,
    dt,
    mk_user,
    plan_premium,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_assert_allowed_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    user = mk_user(now=dt(10))
    users = FakeUserRepo.with_users(user)
    usage = FakeUsageRepo(stats=UsageStats(last_usage=dt(1), daily_usage=0))

    await UserGenerationService.assert_allowed(
        id=user.id,
        repo=users,
        usage=usage,
        catalog=FakeSubscriptionCatalog(),
        at=dt(12),
    )
    assert usage.stats.daily_usage == 0
    assert usage.stats.last_usage == dt(1)

    user.ban(actor=UserRole.OWNER, until=dt(20), at=dt(11))
    with pytest.raises(UserBannedError):
        await UserGenerationService.assert_allowed(
            id=user.id,
            repo=users,
            usage=FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=0)),
            catalog=FakeSubscriptionCatalog(),
            at=dt(12),
        )
    user.unban(actor=UserRole.OWNER, at=dt(12))

    with pytest.raises(LimitViolationError):
        await UserGenerationService.assert_allowed(
            id=user.id,
            repo=users,
            usage=FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=100)),
            catalog=FakeSubscriptionCatalog(),
            at=dt(12),
        )

    with pytest.raises(CooldownViolationError):
        await UserGenerationService.assert_allowed(
            id=user.id,
            repo=users,
            usage=FakeUsageRepo(stats=UsageStats(last_usage=dt(12), daily_usage=0)),
            catalog=FakeSubscriptionCatalog(),
            at=dt(12),
        )

    monkeypatch.setattr(
        "domain.user.services.generation.LimitPolicy.evaluate",
        lambda **_: cast(Any, object()),
    )
    with pytest.raises(ValidationError):
        await UserGenerationService.assert_allowed(
            id=user.id,
            repo=users,
            usage=FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=0)),
            catalog=FakeSubscriptionCatalog(),
            at=dt(12),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_usage_consumes_slot() -> None:
    usage = FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=0))

    await UserGenerationService.record_usage(
        id=UserId(UUID(int=1)),
        usage=usage,
        at=dt(12),
    )

    assert usage.stats.daily_usage == 1
    assert usage.stats.last_usage == dt(12)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_assert_allowed_uses_effective_state_without_mutation() -> None:
    user = mk_user(now=dt(10))
    user.ban(actor=UserRole.OWNER, until=dt(11), at=dt(10))
    user.pull_events()
    users = FakeUserRepo.with_users(user)

    await UserGenerationService.assert_allowed(
        id=user.id,
        repo=users,
        usage=FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=0)),
        catalog=FakeSubscriptionCatalog(),
        at=dt(12),
    )

    assert isinstance(user.state, BannedState)
    assert user.pull_events() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_assert_allowed_uses_effective_subscription_without_mutation() -> None:
    user = mk_user(now=dt(10))
    expired_premium = UserSubscription(
        plan=plan_premium(),
        started_at=dt(10),
        expires_at=dt(11),
    )
    user.change_subscription(actor=UserRole.OWNER, new_subscription=expired_premium, at=dt(10))
    user.pull_events()
    users = FakeUserRepo.with_users(user)

    with pytest.raises(LimitViolationError):
        await UserGenerationService.assert_allowed(
            id=user.id,
            repo=users,
            usage=FakeUsageRepo(
                stats=UsageStats(
                    last_usage=None,
                    daily_usage=FREE_PLAN.daily_limit,
                ),
            ),
            catalog=FakeSubscriptionCatalog(),
            at=dt(12),
        )

    assert user.subscription == expired_premium
    assert user.pull_events() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_assert_allowed_raises_when_user_missing() -> None:
    with pytest.raises(UserNotFoundError):
        await UserGenerationService.assert_allowed(
            id=UserId(UUID(int=404)),
            repo=FakeUserRepo(),
            usage=FakeUsageRepo(),
            catalog=FakeSubscriptionCatalog(),
            at=dt(12),
        )
