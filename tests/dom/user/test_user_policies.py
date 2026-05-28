from datetime import timedelta

import pytest

from domain.catalog import Model, ModelDescriptor, Series, SubscriptionTier, Vendor
from domain.kernel.vo import NonEmptyStr
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
    ModelSelectionAllowed,
    ModelSelectionDenied,
    ModelSelectionPolicy,
    NoBan,
    Unban,
    UsageStats,
    ViolationStats,
)
from domain.user.policies.model_selection import ModelSelectionCode
from domain.user.vo import ActiveState, BannedState, UserProfile, UserRole

from .factories import descriptor_lite, descriptor_pro, dt, subscription_free, subscription_premium


@pytest.mark.unit
def test_limit_policy_decisions_and_validations() -> None:
    denied_daily = LimitPolicy.evaluate(
        subscription=subscription_free(dt(12)),
        stats=UsageStats(last_usage=None, daily_usage=3),
        at=dt(12),
    )
    assert isinstance(denied_daily, LimitDenied)
    assert isinstance(denied_daily.violation, DailyLimitViolation)

    denied_cooldown = LimitPolicy.evaluate(
        subscription=subscription_premium(dt(12)),
        stats=UsageStats(last_usage=dt(12), daily_usage=0),
        at=dt(12),
    )
    assert isinstance(denied_cooldown, LimitDenied)
    assert isinstance(denied_cooldown.violation, CooldownViolation)
    assert denied_cooldown.violation.remaining > timedelta(0)

    allowed = LimitPolicy.evaluate(
        subscription=subscription_free(dt(12)),
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
    free = subscription_free(dt(11))
    premium = subscription_premium(dt(11))
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


@pytest.mark.unit
def test_model_selection_policy_on_premium_subscription() -> None:
    decision = ModelSelectionPolicy.evaluate(
        effective=subscription_premium(dt(12)),
        descriptor=descriptor_pro(),
    )
    assert not isinstance(decision, ModelSelectionDenied)

    denied = ModelSelectionPolicy.evaluate(
        effective=subscription_free(dt(12)),
        descriptor=descriptor_pro(),
    )
    assert isinstance(denied, ModelSelectionDenied)
    assert denied.code == ModelSelectionCode.TIER_TOO_LOW


@pytest.mark.unit
def test_model_selection_policy_allows_free_tier_for_lite() -> None:
    decision = ModelSelectionPolicy.evaluate(
        effective=subscription_free(dt(10)),
        descriptor=descriptor_lite(),
    )
    assert isinstance(decision, ModelSelectionAllowed)


@pytest.mark.unit
def test_model_selection_policy_denies_inactive_model() -> None:
    decision = ModelSelectionPolicy.evaluate(
        effective=subscription_premium(dt(10)),
        descriptor=descriptor_pro(active=False),
    )
    assert isinstance(decision, ModelSelectionDenied)
    assert decision.code == ModelSelectionCode.MODEL_NOT_ACTIVE


@pytest.mark.unit
def test_model_selection_policy_denies_premium_model_on_free() -> None:
    decision = ModelSelectionPolicy.evaluate(
        effective=subscription_free(dt(10)),
        descriptor=descriptor_pro(),
    )
    assert isinstance(decision, ModelSelectionDenied)
    assert decision.code == ModelSelectionCode.TIER_TOO_LOW


@pytest.mark.unit
def test_catalog_model_descriptor_validation_is_enforced() -> None:
    with pytest.raises(ValidationError):
        ModelDescriptor(
            model=Model.parse("gigachat-2-lite"),
            vendor=Vendor.parse("sber"),
            series=Series.parse("gigachat"),
            display_name=" ",
            min_tier=SubscriptionTier.FREE,
        )
