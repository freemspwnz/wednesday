from datetime import timedelta

import pytest

from domain.kernel.vo import NonEmptyStr
from domain.user import (
    ActiveState,
    BannedState,
    ManagementAccessDeniedError,
    StaleWriteError,
    SubscriptionPlan,
    User,
    UserBanExpired,
    UserBanned,
    UserProfile,
    UserProfileChanged,
    UserRole,
    UserRoleChanged,
    UserSubscription,
    UserSubscriptionChanged,
    UserSubscriptionExpired,
    UserUnbanned,
)
from domain.user.events.base import UserEvent
from domain.user.exceptions import InvalidStateTransitionError, ValidationError
from domain.user.policies.management import (
    ChangeRole,
    ManagementAccessCode,
    ManagementAllowed,
    ManagementDenied,
)

from .factories import dt, mk_user


@pytest.mark.unit
def test_user_register_restore_and_ensure() -> None:
    user = mk_user(now=dt(10))
    assert isinstance(user.state, ActiveState)
    assert user.created_at == user.updated_at == user.last_seen_at == dt(10)

    restored = User.restore(
        id=user.id,
        profile=user.profile,
        role=user.role,
        state=user.state,
        subscription=user.subscription,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_seen_at=user.last_seen_at,
    )
    assert User.ensure(restored) is restored


@pytest.mark.unit
def test_user_commands_emit_expected_events() -> None:
    user = mk_user(now=dt(10))

    new_profile = UserProfile(telegram_id=777, is_bot=False, first_name=NonEmptyStr("Updated"))
    user.change_profile(actor=UserRole.SYSTEM, new_profile=new_profile, at=dt(11))
    user.change_role(actor=UserRole.OWNER, new_role=UserRole.ADMIN, at=dt(12))
    user.change_subscription(actor=UserRole.OWNER, new_subscription=UserSubscription.premium(dt(12)), at=dt(12))
    user.ban(actor=UserRole.OWNER, until=dt(14), at=dt(13))
    user.unban(actor=UserRole.OWNER, at=dt(13))

    events = user.pull_events()
    assert [type(evt) for evt in events] == [
        UserProfileChanged,
        UserRoleChanged,
        UserSubscriptionChanged,
        UserBanned,
        UserUnbanned,
    ]


@pytest.mark.unit
def test_user_noop_commands_do_not_touch_updated_at() -> None:
    user = mk_user(now=dt(10))
    at_before = user.updated_at

    user.change_role(actor=UserRole.OWNER, new_role=user.role, at=dt(11))
    user.change_profile(actor=UserRole.SYSTEM, new_profile=user.profile, at=dt(11))
    user.change_subscription(actor=UserRole.ADMIN, new_subscription=user.subscription, at=dt(11))
    user.mark_seen_at(at=dt(10))

    assert user.updated_at == at_before
    assert user.pull_events() == []


@pytest.mark.unit
def test_expire_helpers_emit_events_when_due() -> None:
    user = mk_user(now=dt(10))
    user.ban(actor=UserRole.OWNER, until=dt(11), at=dt(10))
    user.change_subscription(
        actor=UserRole.ADMIN,
        new_subscription=UserSubscription(
            plan=SubscriptionPlan.premium(),
            started_at=dt(10),
            expires_at=dt(11),
        ),
        at=dt(10),
    )
    user.pull_events()

    user.expire_ban_if_due(at=dt(12))
    user.expire_subscription_if_due(at=dt(10) + timedelta(days=2))

    events = user.pull_events()
    assert isinstance(events[0], UserBanExpired)
    assert isinstance(events[1], UserSubscriptionExpired)
    assert isinstance(user.state, ActiveState)
    assert user.subscription.plan.tier.value == 0


@pytest.mark.unit
def test_ban_with_same_until_is_noop() -> None:
    user = mk_user(now=dt(10))
    user.ban(actor=UserRole.OWNER, until=dt(12), at=dt(10))
    user.pull_events()
    updated_at_before = user.updated_at

    user.ban(actor=UserRole.OWNER, until=dt(12), at=dt(11))

    assert user.updated_at == updated_at_before
    assert user.pull_events() == []


@pytest.mark.unit
def test_expire_helpers_tolerate_at_before_updated_at() -> None:
    user = mk_user(now=dt(9), role=UserRole.USER)
    user.ban(actor=UserRole.OWNER, until=dt(10), at=dt(9))
    user.change_subscription(
        actor=UserRole.ADMIN,
        new_subscription=UserSubscription(
            plan=SubscriptionPlan.premium(),
            started_at=dt(9),
            expires_at=dt(10),
        ),
        at=dt(9),
    )
    user.change_role(actor=UserRole.OWNER, new_role=UserRole.ADMIN, at=dt(13))
    user.pull_events()
    updated_at_before = user.updated_at

    user.expire_ban_if_due(at=dt(11))
    user.expire_subscription_if_due(at=dt(11))

    assert isinstance(user.state, ActiveState)
    assert user.subscription.plan.tier.value == 0
    events = user.pull_events()
    assert {type(e) for e in events} == {UserBanExpired, UserSubscriptionExpired}
    assert user.updated_at == updated_at_before


@pytest.mark.unit
def test_user_guardrails_and_errors() -> None:
    user = mk_user(now=dt(10), role=UserRole.USER)
    with pytest.raises(ManagementAccessDeniedError):
        user.change_role(actor=UserRole.USER, new_role=UserRole.ADMIN, at=dt(11))
    with pytest.raises(InvalidStateTransitionError):
        user.unban(actor=UserRole.OWNER, at=dt(11))
    with pytest.raises(StaleWriteError):
        user.mark_seen_at(at=dt(9))
    with pytest.raises(ValidationError):
        user.change_profile(actor=UserRole.SYSTEM, new_profile="bad", at=dt(11))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        user._record_event("bad")  # type: ignore[arg-type]


@pytest.mark.unit
def test_validate_rejects_invalid_events_and_timestamps() -> None:
    user = mk_user(now=dt(10))
    with pytest.raises(ValidationError):
        User.restore(
            id=user.id,
            profile=user.profile,
            role=user.role,
            state=BannedState(until=dt(12)),
            subscription=user.subscription,
            created_at=dt(12),
            updated_at=dt(11),
            last_seen_at=dt(12),
        )

    with pytest.raises(ValidationError):
        User(
            _id=user.id,
            _profile=user.profile,
            _role=user.role,
            _state=user.state,
            _subscription=user.subscription,
            _created_at=dt(10),
            _updated_at=dt(10),
            _last_seen_at=dt(10),
            _events=[UserEvent(user_id=user.id, occurred_at=dt(10)), "bad"],  # type: ignore[list-item]
        )


@pytest.mark.unit
def test_management_unknown_decision_is_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    user = mk_user(now=dt(10))
    action = ChangeRole(old_role=UserRole.USER, new_role=UserRole.ADMIN)

    monkeypatch.setattr("domain.user.user.ManagementAccessPolicy.evaluate", lambda _: object())
    with pytest.raises(ValidationError):
        user._ensure_management_allowed(actor=UserRole.OWNER, action=action)

    monkeypatch.setattr("domain.user.user.ManagementAccessPolicy.evaluate", lambda _: ManagementAllowed())
    user._ensure_management_allowed(actor=UserRole.OWNER, action=action)

    monkeypatch.setattr(
        "domain.user.user.ManagementAccessPolicy.evaluate",
        lambda _: ManagementDenied(code=ManagementAccessCode.ACCESS_DENIED),
    )
    with pytest.raises(ManagementAccessDeniedError):
        user._ensure_management_allowed(actor=UserRole.OWNER, action=action)
