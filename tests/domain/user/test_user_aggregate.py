import pytest

from domain.kernel.vo import NonEmptyStr
from domain.user import (
    AccessDeniedError,
    ActiveState,
    BannedState,
    LimitViolationError,
    SubscriptionChanged,
    User,
    UserBanExpired,
    UserBanned,
    UserBannedError,
    UserNotBannedError,
    UserProfile,
    UserRole,
    UserRoleChanged,
    UserTelegramId,
    UserUnbanned,
    ViolationStats,
)
from domain.user.exceptions import InvalidStateTransitionError, ValidationError
from domain.user.policies import UsageStats
from domain.user.services import SubscriptionCatalog

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
    user.change_subscription(SubscriptionCatalog.premium(), now=dt(11))
    events = user.pull_events()
    assert any(isinstance(e, SubscriptionChanged) for e in events)
    assert user.subscription.tier.value == "premium"


@pytest.mark.unit
def test_change_subscription_same_plan_does_not_emit_event() -> None:
    user = mk_user(now=dt(10))
    plan = user.subscription
    user.change_subscription(plan, now=dt(11))
    assert user.pull_events() == []


@pytest.mark.unit
def test_change_role_requires_permissions() -> None:
    user = mk_user(role=UserRole.ADMIN, now=dt(10))
    with pytest.raises(AccessDeniedError):
        user.change_role(actor=UserRole.USER, new_role=UserRole.USER, now=dt(11))


@pytest.mark.unit
def test_change_role_records_event_on_success() -> None:
    user = mk_user(role=UserRole.USER, now=dt(10))
    user.change_role(actor=UserRole.OWNER, new_role=UserRole.ADMIN, now=dt(11))
    events = user.pull_events()
    assert any(isinstance(e, UserRoleChanged) for e in events)
    assert user.role == UserRole.ADMIN


@pytest.mark.unit
def test_change_role_same_target_raises_validation_error() -> None:
    user = mk_user(role=UserRole.USER, now=dt(10))
    with pytest.raises(ValidationError):
        user.change_role(actor=UserRole.OWNER, new_role=UserRole.USER, now=dt(11))


@pytest.mark.unit
def test_change_role_forbidden_transition_raises() -> None:
    user = mk_user(role=UserRole.OWNER, now=dt(10))
    with pytest.raises(InvalidStateTransitionError):
        user.change_role(actor=UserRole.SYSTEM, new_role=UserRole.SYSTEM, now=dt(11))


@pytest.mark.unit
def test_ensure_can_generate_raises_for_banned_user() -> None:
    user = mk_user(now=dt(10))
    user.apply_manual_ban(actor=UserRole.OWNER, until=dt(15), now=dt(11))
    with pytest.raises(UserBannedError):
        user.ensure_can_generate(stats=UsageStats(last_usage=None, daily_usage=0), now=dt(12))


@pytest.mark.unit
def test_ensure_can_generate_raises_limit_violation() -> None:
    user = mk_user(now=dt(10))
    with pytest.raises(LimitViolationError):
        user.ensure_can_generate(stats=UsageStats(last_usage=None, daily_usage=3), now=dt(12))


@pytest.mark.unit
def test_ensure_can_generate_passes_when_allowed() -> None:
    user = mk_user(now=dt(10))
    user.ensure_can_generate(stats=UsageStats(last_usage=dt(8), daily_usage=0), now=dt(12))


@pytest.mark.unit
def test_manual_ban_and_unban_emit_events() -> None:
    user = mk_user(now=dt(10))
    user.apply_manual_ban(actor=UserRole.OWNER, until=dt(14), now=dt(11))
    user.unban(actor=UserRole.OWNER, now=dt(12))
    events = user.pull_events()
    assert isinstance(events[0], UserBanned)
    assert isinstance(events[1], UserUnbanned)


@pytest.mark.unit
def test_unban_raises_when_user_not_banned() -> None:
    user = mk_user(now=dt(10))
    with pytest.raises(UserNotBannedError):
        user.unban(actor=UserRole.OWNER, now=dt(11))


@pytest.mark.unit
def test_refresh_state_emits_ban_expired_event() -> None:
    user = mk_user(now=dt(10))
    user.apply_manual_ban(actor=UserRole.OWNER, until=dt(11), now=dt(10))
    user.pull_events()
    user.refresh_state(now=dt(12))
    events = user.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], UserBanExpired)
    assert isinstance(user.state, ActiveState)


@pytest.mark.unit
def test_refresh_state_no_change_no_event() -> None:
    user = mk_user(now=dt(10))
    user.refresh_state(now=dt(11))
    assert user.pull_events() == []


@pytest.mark.unit
def test_apply_policy_ban_emits_event_with_system_actor() -> None:
    user = mk_user(now=dt(10))
    user.apply_policy_ban(stats=ViolationStats(today=2, week=2, total=2), now=dt(11))
    event = user.pull_events()[0]
    assert isinstance(event, UserBanned)
    assert event.actor == UserRole.SYSTEM


@pytest.mark.unit
def test_apply_policy_ban_with_no_ban_does_nothing() -> None:
    user = mk_user(now=dt(10))
    user.apply_policy_ban(stats=ViolationStats(today=1, week=1, total=1), now=dt(11))
    assert user.pull_events() == []


@pytest.mark.unit
def test_mark_seen_updates_last_seen_and_updated_at() -> None:
    user = mk_user(now=dt(10))
    user.mark_seen_at(dt(11))
    assert user.last_seen_at == dt(11)
    assert user.updated_at == dt(11)


@pytest.mark.unit
def test_mark_seen_rejects_rollback() -> None:
    user = mk_user(now=dt(10))
    with pytest.raises(ValidationError):
        user.mark_seen_at(dt(9))


@pytest.mark.unit
def test_pull_events_clears_event_buffer() -> None:
    user = mk_user(now=dt(10))
    user.change_subscription(SubscriptionCatalog.premium(), now=dt(11))
    assert len(user.pull_events()) == 1
    assert user.pull_events() == []


@pytest.mark.unit
def test_rehydrate_rejects_invalid_timestamps_order() -> None:
    with pytest.raises(ValidationError):
        User.rehydrate(
            id=UserTelegramId(1),
            profile=UserProfile(is_bot=False, first_name=NonEmptyStr("A")),
            role=UserRole.USER,
            subscription=SubscriptionCatalog.free(),
            state=BannedState(until=dt(12)),
            created_at=dt(12),
            updated_at=dt(11),
            last_seen_at=dt(12),
        )
