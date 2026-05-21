from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from domain.chat import (
    ActiveState,
    Chat,
    ChatEvent,
    ChatId,
    ChatSchedule,
    ChatScheduleSet,
    ManagementContext,
    ScheduleLimitExceededError,
    System,
    ValidationError,
)
from domain.kernel.vo import AwareDatetime

from .factories import default_schedules, dt, mk_chat, owner, private_profile, utc_tz


def cid(n: int = 1) -> ChatId:
    return ChatId(value=UUID(int=n))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("chat_id", "profile", "schedules", "created_at", "updated_at"),
    [
        ("bad", private_profile(), default_schedules(), dt(10), dt(10)),
        (cid(), "bad", default_schedules(), dt(10), dt(10)),
        (cid(), private_profile(), "bad", dt(10), dt(10)),
    ],
    ids=["bad_id_type", "bad_profile_type", "bad_schedules_type"],
)
def test_chat_restore_rejects_invalid_field_types(
    chat_id: object,
    profile: object,
    schedules: object,
    created_at: AwareDatetime,
    updated_at: AwareDatetime,
) -> None:
    with pytest.raises(ValidationError):
        Chat.restore(
            id=chat_id,  # type: ignore[arg-type]
            profile=profile,  # type: ignore[arg-type]
            state=ActiveState(),
            schedules=schedules,  # type: ignore[arg-type]
            created_at=created_at,
            updated_at=updated_at,
        )


@pytest.mark.unit
def test_chat_restore_rejects_invalid_timestamps_order() -> None:
    with pytest.raises(ValidationError):
        Chat.restore(
            id=cid(),
            profile=private_profile(),
            state=ActiveState(),
            schedules=default_schedules(),
            created_at=dt(12),
            updated_at=dt(11),
        )


@pytest.mark.unit
def test_chat_dataclass_rejects_non_event_item() -> None:
    with pytest.raises(ValidationError):
        Chat(
            _id=cid(),
            _profile=private_profile(),
            _state=ActiveState(),
            _schedules=default_schedules(),
            _events=["bad"],  # type: ignore[list-item]
            _created_at=dt(10),
            _updated_at=dt(10),
        )


@pytest.mark.unit
def test_change_profile_rejects_non_actor() -> None:
    chat = mk_chat(now=dt(10))
    new_profile = private_profile(telegram_id=-2002)
    with pytest.raises(ValidationError, match="ManagementActor"):
        chat.change_profile(actor="not-an-actor", new_profile=new_profile, at=dt(11))  # type: ignore[arg-type]


@pytest.mark.unit
def test_management_context_rejects_invalid_actor_type() -> None:
    with pytest.raises(ValidationError):
        ManagementContext(actor="not-an-actor", chat_id=cid())  # type: ignore[arg-type]


@pytest.mark.unit
def test_management_context_rejects_invalid_chat_id_type() -> None:
    with pytest.raises(ValidationError):
        ManagementContext(actor=System(), chat_id=-1)  # type: ignore[arg-type]


@pytest.mark.unit
def test_schedule_set_rejects_too_many_schedules_in_constructor() -> None:
    slots = (
        ChatSchedule(1, 0),
        ChatSchedule(2, 0),
        ChatSchedule(3, 0),
        ChatSchedule(4, 0),
    )
    with pytest.raises(ScheduleLimitExceededError):
        ChatScheduleSet(timezone=utc_tz(), schedules=slots)


@pytest.mark.unit
def test_add_fourth_schedule_via_aggregate_raises() -> None:
    chat = mk_chat(now=dt(10))
    actor = owner()
    chat.add_schedule(actor=actor, schedule=ChatSchedule(1, 0), at=dt(11))
    chat.add_schedule(actor=actor, schedule=ChatSchedule(2, 0), at=dt(12))
    chat.add_schedule(actor=actor, schedule=ChatSchedule(3, 0), at=dt(13))
    chat.pull_events()
    with pytest.raises(ScheduleLimitExceededError):
        chat.add_schedule(actor=actor, schedule=ChatSchedule(4, 0), at=dt(14))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (ChatEvent, {"chat_id": "x", "occurred_at": dt(12)}),
        (ChatEvent, {"chat_id": cid(), "occurred_at": datetime.now(UTC)}),
    ],
    ids=["bad_chat_id", "naive_occurred_at"],
)
def test_chat_event_validates_types(
    factory: Callable[..., Any],
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        factory(**kwargs)
