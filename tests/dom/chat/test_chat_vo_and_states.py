from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from domain.chat import (
    ActiveState,
    ChatId,
    ChatProfile,
    ChatSchedule,
    ChatScheduleSet,
    ChatType,
    InactiveState,
    ValidationError,
    Weekday,
)
from domain.chat.exceptions import InvalidStateTransitionError

from .factories import utc_tz


@pytest.mark.unit
def test_chat_id_rejects_non_uuid_value() -> None:
    with pytest.raises(ValidationError):
        ChatId(value="bad")  # type: ignore[arg-type]


@pytest.mark.unit
def test_chat_id_new_returns_random_uuid() -> None:
    a = ChatId.new()
    b = ChatId.new()
    assert isinstance(a.value, UUID)
    assert a != b


@pytest.mark.unit
def test_chat_profile_rejects_zero_telegram_id() -> None:
    with pytest.raises(ValidationError):
        ChatProfile(type=ChatType.PRIVATE, telegram_id=0)


@pytest.mark.unit
def test_private_chat_profile_without_title_is_valid() -> None:
    p = ChatProfile(type=ChatType.PRIVATE, telegram_id=42)
    assert p.title is None
    assert p.username is None


@pytest.mark.unit
def test_group_profile_requires_title_or_username() -> None:
    with pytest.raises(ValidationError, match="public chat"):
        ChatProfile(type=ChatType.GROUP, telegram_id=-100)


@pytest.mark.unit
def test_group_profile_accepts_title() -> None:
    p = ChatProfile(type=ChatType.GROUP, telegram_id=-100, title="Room")
    assert p.title == "Room"


@pytest.mark.unit
def test_supergroup_profile_accepts_username_only() -> None:
    p = ChatProfile(type=ChatType.SUPERGROUP, telegram_id=-200, username="squad")
    assert p.username == "squad"


@pytest.mark.unit
def test_profile_rejects_title_over_max_length() -> None:
    with pytest.raises(ValidationError, match="title too long"):
        ChatProfile(type=ChatType.PRIVATE, telegram_id=1, title="x" * 256)


@pytest.mark.unit
def test_profile_rejects_username_over_max_length() -> None:
    with pytest.raises(ValidationError, match="username too long"):
        ChatProfile(type=ChatType.PRIVATE, telegram_id=1, username="u" * 33)


@pytest.mark.unit
def test_chat_schedule_validates_hour() -> None:
    with pytest.raises(ValidationError):
        ChatSchedule(24, 0)


@pytest.mark.unit
def test_chat_schedule_validates_minute() -> None:
    with pytest.raises(ValidationError):
        ChatSchedule(12, 60)


@pytest.mark.unit
def test_schedule_set_change_day_is_noop_when_same_weekday() -> None:
    s = ChatScheduleSet(timezone=utc_tz(), weekday=Weekday.WEDNESDAY)
    assert s.change_day(Weekday.WEDNESDAY) is s


@pytest.mark.unit
def test_schedule_set_change_timezone_is_noop_when_same_zone() -> None:
    s = ChatScheduleSet(timezone=utc_tz())
    assert s.change_timezone(utc_tz()) is s


@pytest.mark.unit
def test_schedule_set_add_is_noop_when_duplicate() -> None:
    slot = ChatSchedule(10, 0)
    s = ChatScheduleSet(timezone=utc_tz(), schedules=(slot,))
    assert s.add(slot) is s


@pytest.mark.unit
def test_schedule_set_remove_is_noop_when_missing() -> None:
    s = ChatScheduleSet(timezone=utc_tz())
    assert s.remove(ChatSchedule(1, 0)) is s


@pytest.mark.unit
def test_schedule_set_clear_is_noop_when_empty() -> None:
    s = ChatScheduleSet(timezone=utc_tz())
    assert s.clear() is s


@pytest.mark.unit
def test_schedule_set_clear_preserves_timezone_and_weekday() -> None:
    s = ChatScheduleSet(
        timezone=ZoneInfo("Europe/Berlin"),
        weekday=Weekday.MONDAY,
        schedules=(ChatSchedule(7, 0),),
    )
    cleared = s.clear()
    assert cleared.schedules == ()
    assert cleared.timezone == s.timezone
    assert cleared.weekday == s.weekday


@pytest.mark.unit
def test_active_state_deactivate_returns_inactive() -> None:
    assert isinstance(ActiveState().deactivate(), InactiveState)


@pytest.mark.unit
def test_active_state_activate_raises() -> None:
    with pytest.raises(InvalidStateTransitionError):
        ActiveState().activate()


@pytest.mark.unit
def test_inactive_state_activate_returns_active() -> None:
    assert isinstance(InactiveState().activate(), ActiveState)


@pytest.mark.unit
def test_inactive_state_deactivate_raises() -> None:
    with pytest.raises(InvalidStateTransitionError):
        InactiveState().deactivate()


@pytest.mark.unit
def test_chat_id_uses_provided_uuid() -> None:
    u = uuid4()
    cid = ChatId(value=u)
    assert cid.value is u
