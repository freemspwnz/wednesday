from datetime import timedelta

import pytest

from domain.user import UserRole
from domain.user.policies import (
    BanAssigned,
    BanDurationPolicy,
    CooldownViolation,
    LimitAllowed,
    LimitDenied,
    LimitPolicy,
    ManagementAccessCode,
    ManagementAccessContext,
    ManagementAccessDenied,
    ManagementAccessPolicy,
    UsageStats,
    ViolationStats,
)
from domain.user.services import SubscriptionCatalog

from .factories import dt


@pytest.mark.unit
def test_limit_policy_denies_when_daily_limit_reached() -> None:
    decision = LimitPolicy.evaluate(
        subscription=SubscriptionCatalog.free(),
        stats=UsageStats(last_usage=None, daily_usage=3),
        now=dt(12),
    )
    assert isinstance(decision, LimitDenied)


@pytest.mark.unit
def test_limit_policy_denies_on_cooldown() -> None:
    decision = LimitPolicy.evaluate(
        subscription=SubscriptionCatalog.premium(),
        stats=UsageStats(last_usage=dt(12), daily_usage=0),
        now=dt(12),
    )
    assert isinstance(decision, LimitDenied)
    assert isinstance(decision.violation, CooldownViolation)
    assert decision.violation.remaining > timedelta(0)


@pytest.mark.unit
def test_limit_policy_allows_when_within_limits() -> None:
    decision = LimitPolicy.evaluate(
        subscription=SubscriptionCatalog.free(),
        stats=UsageStats(last_usage=dt(10), daily_usage=0),
        now=dt(12),
    )
    assert isinstance(decision, LimitAllowed)


@pytest.mark.unit
def test_ban_duration_policy_assigns_on_threshold() -> None:
    decision = BanDurationPolicy.evaluate(stats=ViolationStats(today=2, week=2, total=2), now=dt(12))
    assert isinstance(decision, BanAssigned)


@pytest.mark.unit
def test_management_policy_denies_for_user_actor() -> None:
    decision = ManagementAccessPolicy.evaluate(
        ManagementAccessContext(actor_role=UserRole.USER, target_role=UserRole.USER)
    )
    assert isinstance(decision, ManagementAccessDenied)
    assert decision.code is ManagementAccessCode.NOT_ENOUGH_RIGHTS
