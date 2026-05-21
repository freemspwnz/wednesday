from collections.abc import Callable
from typing import Any, cast
from uuid import UUID

import pytest

from domain.chat import (
    ChatActivated,
    ChatDeactivated,
    ChatId,
    ChatMember,
    ChatMemberId,
    ChatMemberRole,
    ChatProfile,
    ChatProfileChanged,
    ChatSchedule,
    ChatScheduleAdded,
    ChatScheduleCleared,
    ChatScheduleDayChanged,
    ChatScheduleRemoved,
    ChatScheduleTimezoneChanged,
    ChatType,
    ManagementActor,
    System,
    Weekday,
)
from domain.chat.exceptions import ValidationError

from .factories import dt, private_profile, utc_tz


def cid(n: int = 1) -> ChatId:
    return ChatId(value=UUID(int=n))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("event_factory", "kwargs"),
    [
        (
            ChatActivated,
            {
                "chat_id": cid(),
                "occurred_at": dt(12),
                "actor": cast(ManagementActor, "system"),
            },
        ),
        (
            ChatProfileChanged,
            {
                "chat_id": cid(),
                "occurred_at": dt(12),
                "old_profile": "bad",
                "new_profile": private_profile(),
                "actor": System(),
            },
        ),
        (
            ChatProfileChanged,
            {
                "chat_id": cid(),
                "occurred_at": dt(12),
                "old_profile": private_profile(),
                "new_profile": "bad",
                "actor": System(),
            },
        ),
        (
            ChatScheduleTimezoneChanged,
            {
                "chat_id": cid(),
                "occurred_at": dt(12),
                "old_timezone": "UTC",
                "new_timezone": utc_tz(),
                "actor": System(),
            },
        ),
        (
            ChatScheduleDayChanged,
            {
                "chat_id": cid(),
                "occurred_at": dt(12),
                "old_weekday": "wednesday",
                "new_weekday": Weekday.FRIDAY,
                "actor": System(),
            },
        ),
        (
            ChatScheduleAdded,
            {
                "chat_id": cid(),
                "occurred_at": dt(12),
                "schedule": "09:00",
                "actor": System(),
            },
        ),
        (
            ChatScheduleRemoved,
            {
                "chat_id": cid(),
                "occurred_at": dt(12),
                "schedule": ChatSchedule(1, 0),
                "actor": cast(ManagementActor, ChatMemberId(1)),
            },
        ),
    ],
    ids=[
        "activated_bad_actor",
        "profile_changed_bad_old_profile",
        "profile_changed_bad_new_profile",
        "timezone_changed_bad_old_zone",
        "day_changed_bad_old_weekday",
        "schedule_added_bad_schedule",
        "schedule_removed_bad_actor",
    ],
)
def test_schedule_and_lifecycle_events_validate_payload(
    event_factory: Callable[..., Any],
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        event_factory(**kwargs)


@pytest.mark.unit
def test_chat_deactivated_validates_actor() -> None:
    with pytest.raises(ValidationError):
        ChatDeactivated(
            chat_id=cid(),
            occurred_at=dt(12),
            actor=cast(ManagementActor, ChatMemberId(1)),
        )


@pytest.mark.unit
def test_chat_schedule_cleared_validates_actor() -> None:
    with pytest.raises(ValidationError):
        ChatScheduleCleared(
            chat_id=cid(),
            occurred_at=dt(12),
            actor=cast(ManagementActor, "admin"),
        )


@pytest.mark.unit
def test_chat_profile_changed_accepts_valid_member_actor() -> None:
    actor = ChatMember(
        id=ChatMemberId(10),
        role=ChatMemberRole.OWNER,
        chat_id=cid(5),
    )
    old = ChatProfile(type=ChatType.PRIVATE, telegram_id=-5)
    new = ChatProfile(type=ChatType.GROUP, telegram_id=-5, title="Squad")
    ev = ChatProfileChanged(
        chat_id=cid(5),
        occurred_at=dt(12),
        old_profile=old,
        new_profile=new,
        actor=actor,
    )
    assert ev.actor == actor
    assert ev.old_profile == old
    assert ev.new_profile == new
