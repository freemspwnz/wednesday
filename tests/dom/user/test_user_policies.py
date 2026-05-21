from datetime import timedelta

import pytest

from domain.kernel.vo import NonEmptyStr
from domain.user import UserProfile, UserRole, UserSubscription
from domain.user.exceptions import ValidationError
from domain.user.policies import (
    Ban,
    BanAssigned,
    BanDuration,
    BanDurationCode,
    BanDurationPolicy,
    ChangeProfile,
    ChangeRole,
    ChangeSubscription,
    CooldownViolation,
    DailyLimitViolation,
    LimitAllowed,
    LimitDenied,
    LimitPolicy,
    ManagementAccessCode,
    ManagementAccessPolicy,
    ManagementContext,
    ManagementDenied,
    NoBan,
    Unban,
    UsageStats,
    ViolationStats,
)
from domain.user.vo import ActiveState, BannedState

from .factories import dt


@pytest.mark.unit
def test_limit_policy_decisions_and_validations() -> None:
    denied_daily = LimitPolicy.evaluate(
        subscription=UserSubscription.free(dt(12)),
        stats=UsageStats(last_usage=None, daily_usage=3),
        at=dt(12),
    )
    assert isinstance(denied_daily, LimitDenied)
    assert isinstance(denied_daily.violation, DailyLimitViolation)

    denied_cooldown = LimitPolicy.evaluate(
        subscription=UserSubscription.premium(dt(12)),
        stats=UsageStats(last_usage=dt(12), daily_usage=0),
        at=dt(12),
    )
    assert isinstance(denied_cooldown, LimitDenied)
    assert isinstance(denied_cooldown.violation, CooldownViolation)
    assert denied_cooldown.violation.remaining > timedelta(0)

    allowed = LimitPolicy.evaluate(
        subscription=UserSubscription.free(dt(12)),
        stats=UsageStats(last_usage=dt(10), daily_usage=0),
        at=dt(12),
    )
    assert isinstance(allowed, LimitAllowed)

    with pytest.raises(ValidationError):
        UsageStats(last_usage=dt(13), daily_usage=0).validate(now=dt(12))


@pytest.mark.unit
def test_ban_duration_policy_paths() -> None:
    assert isinstance(
        BanDurationPolicy.evaluate(stats=ViolationStats(hour=0, today=0, week=0, total=0), at=dt(12)), NoBan
    )
    assert isinstance(
        BanDurationPolicy.evaluate(stats=ViolationStats(hour=2, today=2, week=2, total=2), at=dt(12)), BanAssigned
    )
    assert isinstance(
        BanDurationPolicy.evaluate(stats=ViolationStats(hour=0, today=0, week=5, total=5), at=dt(12)), BanAssigned
    )
    assert isinstance(
        BanDurationPolicy.evaluate(stats=ViolationStats(hour=0, today=3, week=3, total=3), at=dt(12)), BanAssigned
    )
    assert isinstance(
        BanDurationPolicy.evaluate(stats=ViolationStats(hour=0, today=0, week=0, total=10), at=dt(12)), BanAssigned
    )
    assert BanDuration.null() + BanDuration.hour() == BanDuration.hour()
    assert (dt(12) + BanDuration.day()) - dt(12) == timedelta(days=1)
    assert BanDurationCode.BAN_1_DAY.name == "BAN_1_DAY"


@pytest.mark.unit
def test_management_policy_matrix_and_rules() -> None:
    user_profile = UserProfile(telegram_id=1, is_bot=False, first_name=NonEmptyStr("A"))
    free = UserSubscription.free(dt(11))
    premium = UserSubscription.premium(dt(11))
    old_state = ActiveState()
    banned_state = BannedState(until=dt(20))

    allowed = ManagementAccessPolicy.evaluate(
        ManagementContext(
            actor_role=UserRole.OWNER,
            target_role=UserRole.ADMIN,
            action=ChangeRole(old_role=UserRole.ADMIN, new_role=UserRole.USER),
        )
    )
    assert not isinstance(allowed, ManagementDenied)

    denied_context_mismatch = ManagementAccessPolicy.evaluate(
        ManagementContext(
            actor_role=UserRole.OWNER,
            target_role=UserRole.ADMIN,
            action=ChangeRole(old_role=UserRole.USER, new_role=UserRole.USER),
        )
    )
    assert isinstance(denied_context_mismatch, ManagementDenied)
    assert denied_context_mismatch.code is ManagementAccessCode.ACCESS_DENIED

    denied_promote_equal = ManagementAccessPolicy.evaluate(
        ManagementContext(
            actor_role=UserRole.ADMIN,
            target_role=UserRole.USER,
            action=ChangeRole(old_role=UserRole.USER, new_role=UserRole.ADMIN),
        )
    )
    assert isinstance(denied_promote_equal, ManagementDenied)

    denied_downgrade_tier = ManagementAccessPolicy.evaluate(
        ManagementContext(
            actor_role=UserRole.ADMIN,
            target_role=UserRole.USER,
            action=ChangeSubscription(old_subscription=premium, new_subscription=free),
        )
    )
    assert isinstance(denied_downgrade_tier, ManagementDenied)

    assert isinstance(
        ManagementAccessPolicy.evaluate(
            ManagementContext(
                actor_role=UserRole.SYSTEM,
                target_role=UserRole.OWNER,
                action=ChangeProfile(old_profile=user_profile, new_profile=user_profile),
            )
        ),
        type(ManagementAccessPolicy.allow()),
    )
    assert isinstance(
        ManagementAccessPolicy.evaluate(
            ManagementContext(
                actor_role=UserRole.OWNER,
                target_role=UserRole.USER,
                action=Ban(old_state=old_state, until=dt(21)),
            )
        ),
        type(ManagementAccessPolicy.allow()),
    )
    assert isinstance(
        ManagementAccessPolicy.evaluate(
            ManagementContext(
                actor_role=UserRole.OWNER,
                target_role=UserRole.USER,
                action=Unban(old_state=banned_state),
            )
        ),
        type(ManagementAccessPolicy.allow()),
    )
