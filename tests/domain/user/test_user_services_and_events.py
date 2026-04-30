from collections.abc import Callable
from typing import Any, cast

import pytest

from domain.user import SubscriptionTier, UserBanned, UserRole, UserTelegramId, UserUnbanned
from domain.user.events import SubscriptionChanged, UserRoleChanged
from domain.user.exceptions import ValidationError
from domain.user.services import SubscriptionCatalog

from .factories import dt


@pytest.mark.unit
def test_subscription_catalog_presets() -> None:
    free = SubscriptionCatalog.free()
    premium = SubscriptionCatalog.premium()

    assert free.tier == SubscriptionTier.FREE
    assert free.daily_limit == 3
    assert premium.tier == SubscriptionTier.PREMIUM
    assert premium.cooldown_minutes == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event_factory", "kwargs"),
    [
        (
            SubscriptionChanged,
            {
                "user_id": UserTelegramId(1),
                "occurred_at": dt(12),
                "old_plan": "free",
                "new_plan": SubscriptionCatalog.premium(),
            },
        ),
        (
            UserRoleChanged,
            {
                "user_id": UserTelegramId(1),
                "occurred_at": dt(12),
                "old_role": "user",
                "new_role": UserRole.ADMIN,
            },
        ),
        (
            UserBanned,
            {
                "user_id": UserTelegramId(1),
                "occurred_at": dt(12),
                "until": dt(13),
                "actor": "owner",
            },
        ),
    ],
    ids=[
        "subscription_changed_invalid_old_plan",
        "role_changed_invalid_old_role",
        "user_banned_invalid_actor",
    ],
)
def test_events_validate_payload(
    event_factory: Callable[..., Any],
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        event_factory(**kwargs)


@pytest.mark.unit
def test_user_unbanned_event_validates_actor_type() -> None:
    with pytest.raises(ValidationError):
        UserUnbanned(
            user_id=UserTelegramId(1),
            occurred_at=dt(12),
            actor=cast(UserRole, "owner"),
        )
