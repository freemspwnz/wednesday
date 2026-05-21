from collections.abc import Callable
from typing import Any, cast

import pytest

from domain.user import (
    BannedState,
    CooldownViolationError,
    GenerationAccessService,
    LimitViolationError,
    SubscriptionPlan,
    UserBanned,
    UserBannedError,
    UserModerationService,
    UserRole,
    UserUnbanned,
)
from domain.user.events import UserRoleChanged, UserSubscriptionChanged
from domain.user.exceptions import ValidationError
from domain.user.policies import NoBan, UsageStats, ViolationStats
from domain.user.vo import UserSubscription

from .factories import dt, mk_user


@pytest.mark.unit
def test_generation_access_service_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    user = mk_user(now=dt(10))

    GenerationAccessService.assert_generation_allowed(
        user=user,
        stats=UsageStats(last_usage=dt(1), daily_usage=0),
        at=dt(12),
    )

    user.ban(actor=UserRole.OWNER, until=dt(20), at=dt(11))
    with pytest.raises(UserBannedError):
        GenerationAccessService.assert_generation_allowed(
            user=user,
            stats=UsageStats(last_usage=None, daily_usage=0),
            at=dt(12),
        )
    user.unban(actor=UserRole.OWNER, at=dt(12))

    with pytest.raises(LimitViolationError):
        GenerationAccessService.assert_generation_allowed(
            user=user,
            stats=UsageStats(last_usage=None, daily_usage=100),
            at=dt(12),
        )

    with pytest.raises(CooldownViolationError):
        GenerationAccessService.assert_generation_allowed(
            user=user,
            stats=UsageStats(last_usage=dt(12), daily_usage=0),
            at=dt(12),
        )

    monkeypatch.setattr(
        "domain.user.services.generation.LimitPolicy.evaluate",
        lambda **_: cast(Any, object()),
    )
    with pytest.raises(ValidationError):
        GenerationAccessService.assert_generation_allowed(
            user=user,
            stats=UsageStats(last_usage=None, daily_usage=0),
            at=dt(12),
        )


@pytest.mark.unit
def test_generation_access_uses_effective_state_without_mutation() -> None:
    user = mk_user(now=dt(10))
    user.ban(actor=UserRole.OWNER, until=dt(11), at=dt(10))
    user.pull_events()

    GenerationAccessService.assert_generation_allowed(
        user=user,
        stats=UsageStats(last_usage=None, daily_usage=0),
        at=dt(12),
    )

    assert isinstance(user.state, BannedState)
    assert user.pull_events() == []


@pytest.mark.unit
def test_generation_access_uses_effective_subscription_without_mutation() -> None:
    user = mk_user(now=dt(10))
    expired_premium = UserSubscription(
        plan=SubscriptionPlan.premium(),
        started_at=dt(10),
        expires_at=dt(11),
    )
    user.change_subscription(actor=UserRole.OWNER, new_subscription=expired_premium, at=dt(10))
    user.pull_events()

    with pytest.raises(LimitViolationError):
        GenerationAccessService.assert_generation_allowed(
            user=user,
            stats=UsageStats(last_usage=None, daily_usage=SubscriptionPlan.free().daily_limit),
            at=dt(12),
        )

    assert user.subscription == expired_premium
    assert user.pull_events() == []


@pytest.mark.unit
def test_moderation_service_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    user = mk_user(now=dt(10))
    UserModerationService.assign_ban(
        user=user,
        stats=ViolationStats(hour=0, today=0, week=0, total=0),
        at=dt(12),
    )
    assert user.pull_events() == []

    UserModerationService.assign_ban(
        user=user,
        stats=ViolationStats(hour=2, today=2, week=2, total=2),
        at=dt(12),
    )
    assert isinstance(user.pull_events()[0], UserBanned)

    monkeypatch.setattr(
        "domain.user.services.moderation.BanDurationPolicy.evaluate",
        lambda **_: cast(Any, object()),
    )
    with pytest.raises(ValidationError):
        UserModerationService.assign_ban(
            user=user,
            stats=ViolationStats(hour=0, today=0, week=0, total=0),
            at=dt(12),
        )

    with pytest.raises(ValidationError):
        UserModerationService.assign_ban(
            user="bad",  # type: ignore[arg-type]
            stats=ViolationStats(hour=0, today=0, week=0, total=0),
            at=dt(12),
        )

    with pytest.raises(ValidationError):
        UserModerationService.assign_ban(
            user=user,
            stats=cast(Any, "bad"),
            at=dt(12),
        )

    monkeypatch.setattr(
        "domain.user.services.moderation.BanDurationPolicy.evaluate",
        lambda **_: NoBan(),
    )
    UserModerationService.assign_ban(
        user=user,
        stats=ViolationStats(hour=0, today=0, week=0, total=0),
        at=dt(12),
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event_factory", "kwargs"),
    [
        (
            UserSubscriptionChanged,
            {
                "user_id": mk_user().id,
                "occurred_at": dt(12),
                "old_subscription": "free",
                "new_subscription": UserSubscription.premium(dt(12)),
            },
        ),
        (
            UserRoleChanged,
            {
                "user_id": mk_user().id,
                "occurred_at": dt(12),
                "old_role": "user",
                "new_role": UserRole.ADMIN,
            },
        ),
        (
            UserBanned,
            {
                "user_id": mk_user().id,
                "occurred_at": dt(12),
                "until": dt(13),
                "actor": "owner",
            },
        ),
    ],
)
def test_events_validate_payload(event_factory: Callable[..., Any], kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        event_factory(**kwargs)


@pytest.mark.unit
def test_user_unbanned_event_validates_actor_type() -> None:
    with pytest.raises(ValidationError):
        UserUnbanned(user_id=mk_user().id, occurred_at=dt(12), actor=cast(UserRole, "owner"))
