"""Due-slot matching for ChatScheduleSet and Chat (timezone + weekday)."""

from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from domain.chat import (
    Chat,
    ChatId,
    ChatSchedule,
    ChatScheduleSet,
    InactiveState,
    Weekday,
)
from domain.kernel.vo import AwareDatetime

from .factories import mk_chat, private_profile, utc_tz

# 2026-01-07 is Wednesday; 2026-01-01 is Thursday.
_WED_UTC_NOON = AwareDatetime(datetime(2026, 1, 7, 12, 0, tzinfo=UTC))
_WED_UTC_NOON_LATE = AwareDatetime(datetime(2026, 1, 7, 12, 0, 45, tzinfo=UTC))
_THU_UTC_NOON = AwareDatetime(datetime(2026, 1, 1, 12, 0, tzinfo=UTC))


def _set(
    *,
    timezone: ZoneInfo | None = None,
    weekday: Weekday = Weekday.WEDNESDAY,
    hour: int = 12,
    minute: int = 0,
    empty: bool = False,
) -> ChatScheduleSet:
    schedules = () if empty else (ChatSchedule(hour, minute),)
    return ChatScheduleSet(
        timezone=timezone or utc_tz(),
        weekday=weekday,
        schedules=schedules,
    )


@pytest.mark.unit
def test_schedule_set_due_at_utc_slot() -> None:
    assert _set(hour=12, minute=0).is_due_at(_WED_UTC_NOON) is True


@pytest.mark.unit
def test_schedule_set_due_ignores_seconds() -> None:
    assert _set(hour=12, minute=0).is_due_at(_WED_UTC_NOON_LATE) is True


@pytest.mark.unit
def test_schedule_set_due_uses_chat_timezone() -> None:
    moscow = ZoneInfo("Europe/Moscow")
    at_utc_noon = _WED_UTC_NOON  # 15:00 in Moscow
    assert _set(timezone=moscow, hour=15, minute=0).is_due_at(at_utc_noon) is True
    assert _set(timezone=moscow, hour=12, minute=0).is_due_at(at_utc_noon) is False


@pytest.mark.unit
def test_schedule_set_not_due_on_other_weekday() -> None:
    assert _set(hour=12, minute=0).is_due_at(_THU_UTC_NOON) is False


@pytest.mark.unit
def test_schedule_set_not_due_when_empty() -> None:
    assert _set(empty=True).is_due_at(_WED_UTC_NOON) is False


@pytest.mark.unit
def test_chat_due_when_active_and_slot_matches() -> None:
    chat = Chat.register(
        id=ChatId(value=UUID(int=7)),
        profile=private_profile(),
        schedules=_set(hour=12, minute=0),
        at=_WED_UTC_NOON,
    )
    assert chat.is_due_at(_WED_UTC_NOON) is True


@pytest.mark.unit
def test_chat_not_due_when_inactive() -> None:
    now = _WED_UTC_NOON
    chat = Chat.restore(
        id=ChatId(value=UUID(int=7)),
        profile=private_profile(),
        state=InactiveState(),
        schedules=_set(hour=12, minute=0),
        created_at=now,
        updated_at=now,
    )
    assert chat.is_due_at(now) is False


@pytest.mark.unit
def test_registered_chat_without_slots_is_not_due() -> None:
    chat = mk_chat(now=_WED_UTC_NOON)
    assert chat.is_due_at(_WED_UTC_NOON) is False
