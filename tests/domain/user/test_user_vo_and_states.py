from uuid import UUID

import pytest

import domain.user as user_api
from domain.kernel.vo import NonEmptyStr
from domain.user import ActiveState, BannedState, UserId, UserProfile
from domain.user.exceptions import InvalidStateTransitionError, ValidationError

from .factories import dt


@pytest.mark.unit
def test_user_id_and_profile_helpers() -> None:
    user_id = UserId(UUID(int=7))
    assert str(user_id) == str(UUID(int=7))
    assert isinstance(UserId.new(), UserId)
    with pytest.raises(ValidationError):
        UserId.ensure("bad")  # type: ignore[arg-type]

    profile = UserProfile(
        telegram_id=123,
        is_bot=False,
        first_name=NonEmptyStr("Jane"),
        last_name=NonEmptyStr("Doe"),
    )
    assert str(profile.full_name) == "Jane Doe"
    with pytest.raises(ValidationError):
        UserProfile(telegram_id=0, is_bot=False, first_name=NonEmptyStr("A"))
    with pytest.raises(ValidationError):
        UserProfile(telegram_id=1, is_bot=False, first_name=NonEmptyStr("A"), username="a" * 65)


@pytest.mark.unit
def test_state_and_subscription_helpers() -> None:
    state = BannedState(until=dt(12))
    assert state.is_banned_at(dt(11))
    assert isinstance(state.effective_at(now=dt(13)), ActiveState)
    assert isinstance(ActiveState().ban_until(until=dt(13), now=dt(12)), BannedState)
    with pytest.raises(ValidationError):
        ActiveState().ban_until(until=dt(12), now=dt(12))
    with pytest.raises(InvalidStateTransitionError):
        BannedState(until=dt(13)).ban_until(until=dt(12), now=dt(11))


@pytest.mark.unit
def test_public_init_exports_are_minimal_and_stable() -> None:
    expected = {
        "User",
        "UserRepo",
        "UserId",
        "UserRole",
        "UserProfile",
        "UserSubscription",
        "SubscriptionPlan",
        "SubscriptionTier",
        "ActiveState",
        "BannedState",
        "UserEvent",
        "GenerationAccessService",
        "UserModerationService",
    }
    for name in expected:
        assert hasattr(user_api, name), name
    assert not hasattr(user_api, "AccessDeniedError")
