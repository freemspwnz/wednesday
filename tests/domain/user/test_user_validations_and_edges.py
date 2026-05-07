from datetime import UTC, datetime, timedelta

import pytest

from domain.kernel.vo import NonEmptyStr
from domain.user import SubscriptionPlan, SubscriptionTier, User, UserId, UserProfile, UserRole
from domain.user.events.base import UserEvent
from domain.user.events.moderation import UserBanned
from domain.user.exceptions import InvalidStateTransitionError, ValidationError
from domain.user.policies.ban_duration.vo import BanAssigned, BanDurationCode, ViolationStats
from domain.user.policies.limit.vo import LimitDenied
from domain.user.policies.limit.vo.violations import CooldownViolation, DailyLimitViolation
from domain.user.policies.management.vo.decisions import ManagementDenied
from domain.user.repo import UserRepo
from domain.user.vo import ActiveState, BannedState, UserSubscription

from .factories import dt, mk_user


@pytest.mark.unit
def test_events_and_model_validations() -> None:
    with pytest.raises(ValidationError):
        UserEvent(user_id="bad", occurred_at=dt(12))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        UserEvent(user_id=mk_user().id, occurred_at=datetime.now(UTC))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        UserBanned(user_id=mk_user().id, occurred_at=dt(12), until="bad", actor=UserRole.OWNER)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        User(
            _id=mk_user().id,
            _profile=UserProfile(telegram_id=1, is_bot=False, first_name=NonEmptyStr("A")),
            _role=UserRole.USER,
            _subscription=UserSubscription.free(dt(12)),
            _events=["bad"],  # type: ignore[list-item]
            _state=ActiveState(),
            _created_at=dt(12),
            _updated_at=dt(12),
            _last_seen_at=dt(12),
        )


@pytest.mark.unit
def test_value_objects_and_states_validations() -> None:
    with pytest.raises(ValidationError):
        UserId(value="bad")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        SubscriptionPlan(tier="free", daily_limit=1, cooldown_minutes=1)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        SubscriptionPlan(tier=SubscriptionTier.FREE, daily_limit=-1, cooldown_minutes=1)
    with pytest.raises(ValidationError):
        SubscriptionPlan(tier=SubscriptionTier.FREE, daily_limit=1, cooldown_minutes=-1)
    with pytest.raises(ValidationError):
        UserSubscription(plan=SubscriptionPlan.free(), started_at=dt(12), expires_at=dt(12))
    with pytest.raises(InvalidStateTransitionError):
        ActiveState().unban()
    with pytest.raises(ValidationError):
        BannedState(until="bad")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        BannedState(until=dt(14)).ban_until(until=dt(12), now=dt(12))


@pytest.mark.unit
def test_policy_vos_and_decisions_validate_types() -> None:
    with pytest.raises(ValidationError):
        ViolationStats(hour=2, today=1, week=2, total=2)
    with pytest.raises(ValidationError):
        DailyLimitViolation(daily_limit=-1, used=0)
    with pytest.raises(ValidationError):
        CooldownViolation(cooldown_minutes=1, remaining=timedelta(seconds=-1))
    with pytest.raises(ValidationError):
        LimitDenied(violation="bad")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ManagementDenied(code="bad")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        BanAssigned(banned_until="bad", code=BanDurationCode.BAN_1_HOUR)  # type: ignore[arg-type]


@pytest.mark.unit
def test_repo_protocol_shape() -> None:
    assert hasattr(UserRepo, "get_by_id")
    assert hasattr(UserRepo, "save")
    assert hasattr(UserRepo, "exists")
