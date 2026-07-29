from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from domain.kernel.vo import NonEmptyStr
from domain.user import (
    ActiveState,
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
from domain.user.events import UserSettingsChanged
from domain.user.events.base import UserEvent
from domain.user.exceptions import ValidationError

from .factories import (
    default_settings,
    descriptor_pro,
    dt,
    mk_user,
    plan_free,
    plan_premium,
    subscription_free,
    subscription_premium,
)


@pytest.mark.unit
def test_user_event_base_and_payload_validation() -> None:
    with pytest.raises(ValidationError):
        UserEvent(user_id="bad", occurred_at=dt(12))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        UserEvent(user_id=mk_user().id, occurred_at=datetime.now(UTC))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        UserBanned(user_id=mk_user().id, occurred_at=dt(12), until="bad", actor=UserRole.OWNER)  # type: ignore[arg-type]


@pytest.mark.unit
def test_user_settings_changed_event_emitted_by_change_settings() -> None:
    user = mk_user(now=dt(10))
    user.change_subscription(
        actor=UserRole.OWNER,
        new_subscription=subscription_premium(dt(10)),
        at=dt(10),
    )
    user.pull_events()

    user.change_settings(fallback=plan_free(), descriptor=descriptor_pro(), at=dt(11))

    events = user.pull_events()
    assert len(events) == 1
    event = events[0]
    assert isinstance(event, UserSettingsChanged)
    assert event.old_settings == default_settings()
    assert event.new_settings == user.settings


@pytest.mark.unit
def test_user_commands_emit_expected_events() -> None:
    user = mk_user(now=dt(10))

    new_profile = UserProfile(telegram_id=777, is_bot=False, first_name=NonEmptyStr("Updated"))
    user.change_profile(actor=UserRole.SYSTEM, new_profile=new_profile, at=dt(11))
    user.change_role(actor=UserRole.OWNER, new_role=UserRole.ADMIN, at=dt(12))
    user.change_subscription(actor=UserRole.OWNER, new_subscription=subscription_premium(dt(12)), at=dt(12))
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
def test_expire_helpers_emit_events_when_due() -> None:
    user = mk_user(now=dt(10))
    user.ban(actor=UserRole.OWNER, until=dt(11), at=dt(10))
    user.change_subscription(
        actor=UserRole.ADMIN,
        new_subscription=UserSubscription(
            plan=plan_premium(),
            started_at=dt(10),
            expires_at=dt(11),
        ),
        at=dt(10),
    )
    user.pull_events()

    user.expire_ban_if_due(at=dt(12))
    user.expire_subscription_if_due(fallback=plan_free(), at=dt(10) + timedelta(days=2))

    events = user.pull_events()
    assert isinstance(events[0], UserBanExpired)
    assert isinstance(events[1], UserSubscriptionExpired)
    assert isinstance(user.state, ActiveState)
    assert user.subscription.plan.tier.value == 0


@pytest.mark.unit
def test_expire_helpers_tolerate_at_before_updated_at_and_emit_events() -> None:
    user = mk_user(now=dt(9), role=UserRole.USER)
    user.ban(actor=UserRole.OWNER, until=dt(10), at=dt(9))
    user.change_subscription(
        actor=UserRole.ADMIN,
        new_subscription=UserSubscription(
            plan=plan_premium(),
            started_at=dt(9),
            expires_at=dt(10),
        ),
        at=dt(9),
    )
    user.change_role(actor=UserRole.OWNER, new_role=UserRole.ADMIN, at=dt(13))
    user.pull_events()
    updated_at_before = user.updated_at

    user.expire_ban_if_due(at=dt(11))
    user.expire_subscription_if_due(fallback=plan_free(), at=dt(11))

    assert isinstance(user.state, ActiveState)
    assert user.subscription.plan.tier.value == 0
    events = user.pull_events()
    assert {type(e) for e in events} == {UserBanExpired, UserSubscriptionExpired}
    assert user.updated_at == updated_at_before


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
                "new_subscription": subscription_premium(dt(12)),
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


@pytest.mark.unit
def test_user_rejects_invalid_internal_event_list_payload() -> None:
    with pytest.raises(ValidationError):
        User(
            _id=mk_user().id,
            _profile=UserProfile(telegram_id=1, is_bot=False, first_name=NonEmptyStr("A")),
            _role=UserRole.USER,
            _subscription=subscription_free(dt(12)),
            _settings=default_settings(),
            _events=["bad"],  # type: ignore[list-item]
            _state=mk_user().state,
            _created_at=dt(12),
            _updated_at=dt(12),
            _last_seen_at=dt(12),
        )
