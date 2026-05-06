import pytest

from domain.kernel.vo import NonEmptyStr
from domain.user import (
    AccessDeniedError,
    ActiveState,
    BannedState,
    User,
    UserBanExpired,
    UserBanned,
    UserProfile,
    UserRole,
    UserRoleChanged,
    UserSubscriptionChanged,
    UserTelegramId,
    UserUnbanned,
)
from domain.user.exceptions import InvalidStateTransitionError, ValidationError
from domain.user.vo import UserSubscription

from .factories import dt, mk_user


@pytest.mark.unit
def test_create_sets_active_state_and_timestamps() -> None:
    user = mk_user(now=dt(10))
    assert user.created_at == dt(10)
    assert user.updated_at == dt(10)
    assert isinstance(user.state, ActiveState)


@pytest.mark.unit
def test_change_subscription_records_event() -> None:
    user = mk_user(now=dt(10))
    changed = user.change_subscription(
        actor=UserRole.ADMIN, new_subscription=UserSubscription.premium(dt(11)), at=dt(11)
    )
    events = user.pull_events()
    assert changed is True
    assert any(isinstance(e, UserSubscriptionChanged) for e in events)
    assert user.subscription.plan.tier.value == 1


@pytest.mark.unit
def test_change_subscription_same_plan_denied_by_policy() -> None:
    user = mk_user(now=dt(10))
    plan = user.subscription
    with pytest.raises(AccessDeniedError):
        user.change_subscription(actor=UserRole.ADMIN, new_subscription=plan, at=dt(11))


@pytest.mark.unit
def test_change_role_requires_permissions() -> None:
    user = mk_user(role=UserRole.ADMIN, now=dt(10))
    with pytest.raises(AccessDeniedError):
        user.change_role(actor=UserRole.USER, new_role=UserRole.USER, at=dt(11))


@pytest.mark.unit
def test_change_role_records_event_on_success() -> None:
    user = mk_user(role=UserRole.USER, now=dt(10))
    changed = user.change_role(actor=UserRole.OWNER, new_role=UserRole.ADMIN, at=dt(11))
    events = user.pull_events()
    assert changed is True
    assert any(isinstance(e, UserRoleChanged) for e in events)
    assert user.role == UserRole.ADMIN


@pytest.mark.unit
def test_change_role_same_target_denied_by_policy() -> None:
    user = mk_user(role=UserRole.USER, now=dt(10))
    with pytest.raises(AccessDeniedError):
        user.change_role(actor=UserRole.OWNER, new_role=UserRole.USER, at=dt(11))


@pytest.mark.unit
def test_change_role_forbidden_transition_raises() -> None:
    user = mk_user(role=UserRole.OWNER, now=dt(10))
    with pytest.raises(AccessDeniedError):
        user.change_role(actor=UserRole.SYSTEM, new_role=UserRole.SYSTEM, at=dt(11))


@pytest.mark.unit
def test_ban_and_unban_emit_events() -> None:
    user = mk_user(now=dt(10))
    user.ban(actor=UserRole.OWNER, until=dt(14), at=dt(11))
    user.unban(actor=UserRole.OWNER, at=dt(12))
    events = user.pull_events()
    assert isinstance(events[0], UserBanned)
    assert isinstance(events[1], UserUnbanned)


@pytest.mark.unit
def test_unban_raises_when_user_active() -> None:
    user = mk_user(now=dt(10))
    with pytest.raises(InvalidStateTransitionError):
        user.unban(actor=UserRole.OWNER, at=dt(11))


@pytest.mark.unit
def test_refresh_state_emits_ban_expired_event() -> None:
    user = mk_user(now=dt(10))
    user.ban(actor=UserRole.OWNER, until=dt(11), at=dt(10))
    user.pull_events()
    changed = user.expire_ban_if_due(at=dt(12))
    events = user.pull_events()
    assert changed is True
    assert len(events) == 1
    assert isinstance(events[0], UserBanExpired)
    assert isinstance(user.state, ActiveState)


@pytest.mark.unit
def test_expire_ban_no_change_no_event() -> None:
    user = mk_user(now=dt(10))
    changed = user.expire_ban_if_due(at=dt(11))
    assert changed is False
    assert user.pull_events() == []


@pytest.mark.unit
def test_mark_seen_updates_last_seen_and_updated_at() -> None:
    user = mk_user(now=dt(10))
    changed = user.mark_seen_at(at=dt(11))
    assert changed is True
    assert user.last_seen_at == dt(11)
    assert user.updated_at == dt(11)


@pytest.mark.unit
def test_mark_seen_rejects_rollback() -> None:
    user = mk_user(now=dt(10))
    with pytest.raises(ValidationError):
        user.mark_seen_at(at=dt(9))


@pytest.mark.unit
def test_pull_events_clears_event_buffer() -> None:
    user = mk_user(now=dt(10))
    user.change_subscription(actor=UserRole.ADMIN, new_subscription=UserSubscription.premium(dt(11)), at=dt(11))
    assert len(user.pull_events()) == 1
    assert user.pull_events() == []


@pytest.mark.unit
def test_rehydrate_rejects_invalid_timestamps_order() -> None:
    with pytest.raises(ValidationError):
        User.rehydrate(
            id=UserTelegramId(1),
            profile=UserProfile(is_bot=False, first_name=NonEmptyStr("A")),
            role=UserRole.USER,
            subscription=UserSubscription.free(dt(12)),
            state=BannedState(until=dt(12)),
            created_at=dt(12),
            updated_at=dt(11),
            last_seen_at=dt(12),
        )
