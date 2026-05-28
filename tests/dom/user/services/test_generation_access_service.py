from __future__ import annotations

from typing import Any, cast

import pytest

from domain.user import (
    BannedState,
    CooldownViolationError,
    GenerationAccessService,
    LimitViolationError,
    UserBannedError,
    UserRole,
)
from domain.user.exceptions import ValidationError
from domain.user.policies import UsageStats
from domain.user.vo import UserSubscription

from ..factories import FREE_PLAN, FakeSubscriptionCatalog, FakeUsageRepo, dt, mk_user, plan_premium


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_access_service_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    user = mk_user(now=dt(10))

    await GenerationAccessService.assert_generation_allowed(
        user=user,
        repo=FakeUsageRepo(stats=UsageStats(last_usage=dt(1), daily_usage=0)),
        catalog=FakeSubscriptionCatalog(),
        at=dt(12),
    )

    user.ban(actor=UserRole.OWNER, until=dt(20), at=dt(11))
    with pytest.raises(UserBannedError):
        await GenerationAccessService.assert_generation_allowed(
            user=user,
            repo=FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=0)),
            catalog=FakeSubscriptionCatalog(),
            at=dt(12),
        )
    user.unban(actor=UserRole.OWNER, at=dt(12))

    with pytest.raises(LimitViolationError):
        await GenerationAccessService.assert_generation_allowed(
            user=user,
            repo=FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=100)),
            catalog=FakeSubscriptionCatalog(),
            at=dt(12),
        )

    with pytest.raises(CooldownViolationError):
        await GenerationAccessService.assert_generation_allowed(
            user=user,
            repo=FakeUsageRepo(stats=UsageStats(last_usage=dt(12), daily_usage=0)),
            catalog=FakeSubscriptionCatalog(),
            at=dt(12),
        )

    monkeypatch.setattr(
        "domain.user.services.generation.LimitPolicy.evaluate",
        lambda **_: cast(Any, object()),
    )
    with pytest.raises(ValidationError):
        await GenerationAccessService.assert_generation_allowed(
            user=user,
            repo=FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=0)),
            catalog=FakeSubscriptionCatalog(),
            at=dt(12),
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_access_uses_effective_state_without_mutation() -> None:
    user = mk_user(now=dt(10))
    user.ban(actor=UserRole.OWNER, until=dt(11), at=dt(10))
    user.pull_events()

    await GenerationAccessService.assert_generation_allowed(
        user=user,
        repo=FakeUsageRepo(stats=UsageStats(last_usage=None, daily_usage=0)),
        catalog=FakeSubscriptionCatalog(),
        at=dt(12),
    )

    assert isinstance(user.state, BannedState)
    assert user.pull_events() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generation_access_uses_effective_subscription_without_mutation() -> None:
    user = mk_user(now=dt(10))
    expired_premium = UserSubscription(
        plan=plan_premium(),
        started_at=dt(10),
        expires_at=dt(11),
    )
    user.change_subscription(actor=UserRole.OWNER, new_subscription=expired_premium, at=dt(10))
    user.pull_events()

    with pytest.raises(LimitViolationError):
        await GenerationAccessService.assert_generation_allowed(
            user=user,
            repo=FakeUsageRepo(
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
