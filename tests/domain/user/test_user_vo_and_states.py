import pytest

from domain.kernel.vo import NonEmptyStr
from domain.user import ActiveState, BannedState, UserProfile, UserTelegramId
from domain.user.exceptions import ValidationError

from .factories import dt


@pytest.mark.unit
def test_user_telegram_id_validates_positive_value() -> None:
    with pytest.raises(ValidationError):
        UserTelegramId(0)


@pytest.mark.unit
def test_user_profile_full_name_builds_from_first_and_last_name() -> None:
    profile = UserProfile(is_bot=False, first_name=NonEmptyStr("Jane"), last_name=NonEmptyStr("Doe"))
    assert str(profile.full_name) == "Jane Doe"


@pytest.mark.unit
def test_banned_state_refresh_unbans_after_until() -> None:
    state = BannedState(until=dt(12))
    assert isinstance(state.refresh(now=dt(13)), ActiveState)
