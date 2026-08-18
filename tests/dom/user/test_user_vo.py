from uuid import UUID

import pytest

import domain.user as user_api
from domain.catalog import Model, ModelDescriptor, Series, SubscriptionTier, Vendor
from domain.kernel.vo import NonEmptyStr
from domain.user import ActiveState, BannedState, UserId, UserProfile
from domain.user.exceptions import InvalidStateTransitionError, ValidationError
from domain.user.vo import UserSettings

from .factories import default_settings, descriptor_lite, dt


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
def test_model_vendor_series_and_settings_helpers() -> None:
    assert str(Model.parse("GigaChat-2-Lite")) == "gigachat-2-lite"
    settings = default_settings()
    assert settings == UserSettings.from_descriptor(descriptor_lite())
    with pytest.raises(ValidationError):
        Model.parse("bad slug")


@pytest.mark.unit
def test_model_descriptor_and_settings_from_descriptor_validate() -> None:
    descriptor = descriptor_lite()
    settings = UserSettings.from_descriptor(descriptor)
    assert settings.model == descriptor.model
    assert settings.vendor == descriptor.vendor
    assert settings.series == descriptor.series

    with pytest.raises(ValidationError):
        ModelDescriptor(
            model=Model.parse("gigachat-2-lite"),
            vendor=Vendor.parse("sber"),
            series=Series.parse("gigachat"),
            display_name=" ",
            min_tier=SubscriptionTier.FREE,
        )


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
        "ActiveState",
        "BannedState",
        "UserEvent",
        "UsageStats",
        "ViolationStats",
    }
    for name in expected:
        assert hasattr(user_api, name), name
    assert hasattr(user_api, "AccessDeniedError")
