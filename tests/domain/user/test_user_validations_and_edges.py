from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from domain.kernel.vo import NonEmptyStr
from domain.user import (
    ActiveState,
    BannedState,
    SubscriptionPlan,
    SubscriptionTier,
    User,
    UserProfile,
    UserRole,
    UserTelegramId,
)
from domain.user.events.base import UserEvent
from domain.user.events.lifecycle import UserBanned
from domain.user.exceptions import InvalidStateTransitionError, ValidationError
from domain.user.policies.ban_duration.vo import BanAssigned, BanDuration, BanDurationCode, ViolationStats
from domain.user.policies.limit.vo.decisions import LimitDenied
from domain.user.policies.limit.vo.violations import CooldownViolation, DailyLimitViolation
from domain.user.policies.management.vo.decisions import ManagementDenied
from domain.user.vo import UserSubscription

from .factories import dt, mk_user


@pytest.mark.unit
@pytest.mark.parametrize(
    ("user_id", "occurred_at"),
    [
        ("1", dt(12)),
        (UserTelegramId(1), datetime.now(UTC)),
    ],
    ids=["invalid_user_id", "invalid_occurred_at_type"],
)
def test_user_event_validates_types(user_id: object, occurred_at: object) -> None:
    with pytest.raises(ValidationError):
        UserEvent(user_id=user_id, occurred_at=occurred_at)  # type: ignore[arg-type]


@pytest.mark.unit
def test_aggregate_rejects_non_subscription_plan_on_change() -> None:
    user = mk_user()
    with pytest.raises(ValidationError):
        user.change_subscription(actor=UserRole.ADMIN, new_subscription="premium", at=dt(13))  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("actor", "new_role"),
    [
        ("owner", UserRole.ADMIN),
        (UserRole.OWNER, "admin"),
    ],
    ids=["invalid_actor_type", "invalid_new_role_type"],
)
def test_aggregate_rejects_invalid_change_role_types(actor: object, new_role: object) -> None:
    user = mk_user()
    with pytest.raises(ValidationError):
        user.change_role(actor=actor, new_role=new_role, at=dt(13))  # type: ignore[arg-type]


@pytest.mark.unit
def test_mark_seen_checks_updated_at_monotonicity() -> None:
    user = mk_user(now=dt(10))
    user.change_subscription(actor=UserRole.ADMIN, new_subscription=UserSubscription.premium(dt(12)), at=dt(12))
    with pytest.raises(ValidationError):
        user.mark_seen_at(at=dt(11))


@pytest.mark.unit
def test_mark_seen_rejects_non_aware_datetime() -> None:
    user = mk_user()
    with pytest.raises(ValidationError):
        user.mark_seen_at(at=datetime.now(UTC))  # type: ignore[arg-type]


@pytest.mark.unit
def test_user_dataclass_rejects_non_event_item() -> None:
    with pytest.raises(ValidationError):
        User(
            _id=UserTelegramId(1),
            _profile=UserProfile(is_bot=False, first_name=NonEmptyStr("A")),
            _role=UserRole.USER,
            _subscription=UserSubscription.free(dt(12)),
            _events=["bad"],  # type: ignore[list-item]
            _state=ActiveState(),
            _created_at=dt(12),
            _updated_at=dt(12),
            _last_seen_at=dt(12),
        )


@pytest.mark.unit
def test_subscription_plan_validates_tier_type() -> None:
    with pytest.raises(ValidationError):
        SubscriptionPlan(tier="free", daily_limit=1, cooldown_minutes=1)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("daily_limit", "cooldown_minutes"),
    [
        (-1, 1),
        (1, -1),
    ],
    ids=["negative_daily_limit", "negative_cooldown_minutes"],
)
def test_subscription_plan_validates_non_negative_limits(daily_limit: int, cooldown_minutes: int) -> None:
    with pytest.raises(ValidationError):
        SubscriptionPlan(tier=SubscriptionTier.FREE, daily_limit=daily_limit, cooldown_minutes=cooldown_minutes)


@pytest.mark.unit
def test_active_state_unban_raises_invalid_transition() -> None:
    with pytest.raises(InvalidStateTransitionError):
        ActiveState().unban()


@pytest.mark.unit
def test_active_state_refresh_returns_same_object() -> None:
    state = ActiveState()
    assert state.effective_at(dt(12), ActiveState()) is state


@pytest.mark.unit
def test_banned_state_validates_until_type() -> None:
    with pytest.raises(ValidationError):
        BannedState(until="bad")  # type: ignore[arg-type]


@pytest.mark.unit
def test_banned_state_rejects_non_future_extension() -> None:
    state = BannedState(until=dt(14))
    with pytest.raises(ValidationError):
        state.ban_until(until=dt(12), now=dt(12))


@pytest.mark.unit
def test_banned_state_unban_returns_active_state() -> None:
    assert isinstance(BannedState(until=dt(14)).unban(), ActiveState)


@pytest.mark.unit
def test_banned_state_refresh_keeps_state_before_expiry() -> None:
    state = BannedState(until=dt(14))
    assert state.effective_at(now=dt(13), fallback=ActiveState()) == state


@pytest.mark.unit
def test_ban_duration_builders_and_addition_variants() -> None:
    assert BanDuration.null().value == timedelta(0)
    assert BanDuration.day().value == timedelta(days=1)
    assert BanDuration.week().value == timedelta(weeks=1)
    assert BanDuration.month().value == timedelta(days=30)
    assert BanDuration.year().value == timedelta(days=365)
    assert BanDuration.hour() + BanDuration.hour() == BanDuration(value=timedelta(hours=2))
    # Operator invalid-type checks are covered by mypy; runtime only verifies valid paths.


@pytest.mark.unit
@pytest.mark.parametrize(
    ("today", "week", "total"),
    [
        ("1", 1, 1),
        (1, "1", 1),
        (1, 1, "1"),
        (-1, 1, 1),
        (1, -1, 1),
        (1, 1, -1),
        (2, 1, 2),
        (1, 3, 2),
    ],
    ids=[
        "today_not_int",
        "week_not_int",
        "total_not_int",
        "today_negative",
        "week_negative",
        "total_negative",
        "today_gt_week",
        "week_gt_total",
    ],
)
def test_violation_stats_validation_edges(today: object, week: object, total: object) -> None:
    with pytest.raises(ValidationError):
        ViolationStats(hour=0, today=today, week=week, total=total)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("daily_limit", "used"),
    [
        ("3", 1),
        (3, "1"),
        (-1, 1),
        (1, -1),
    ],
    ids=[
        "daily_limit_not_int",
        "used_not_int",
        "daily_limit_negative",
        "used_negative",
    ],
)
def test_daily_limit_violation_validation(daily_limit: object, used: object) -> None:
    with pytest.raises(ValidationError):
        DailyLimitViolation(daily_limit=daily_limit, used=used)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("cooldown_minutes", "remaining"),
    [
        ("1", timedelta(seconds=1)),
        (1, 1),
        (-1, timedelta(seconds=1)),
        (1, timedelta(seconds=-1)),
    ],
    ids=[
        "cooldown_not_int",
        "remaining_not_timedelta",
        "cooldown_negative",
        "remaining_negative",
    ],
)
def test_cooldown_violation_validation(cooldown_minutes: object, remaining: object) -> None:
    with pytest.raises(ValidationError):
        CooldownViolation(cooldown_minutes=cooldown_minutes, remaining=remaining)  # type: ignore[arg-type]


@pytest.mark.unit
def test_limit_violation_codes() -> None:
    assert DailyLimitViolation(daily_limit=3, used=3).code.value == "daily_limit_exceeded"
    assert CooldownViolation(cooldown_minutes=1, remaining=timedelta(seconds=1)).code.value == "cooldown"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (LimitDenied, {"violation": "bad"}),
        (ManagementDenied, {"code": "bad"}),
        (BanAssigned, {"banned_until": "bad", "code": BanDurationCode.BAN_1_HOUR}),
        (BanAssigned, {"banned_until": dt(13), "code": "bad"}),
    ],
    ids=[
        "limit_denied_bad_violation",
        "management_denied_bad_code",
        "ban_assigned_bad_banned_until",
        "ban_assigned_bad_code",
    ],
)
def test_decision_objects_validate_types(
    factory: Callable[..., Any],
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        factory(**kwargs)


@pytest.mark.unit
def test_user_banned_event_validates_until_type() -> None:
    with pytest.raises(ValidationError):
        UserBanned(
            user_id=UserTelegramId(1),
            occurred_at=dt(12),
            until="bad",  # type: ignore[arg-type]
            actor=UserRole.OWNER,
        )
