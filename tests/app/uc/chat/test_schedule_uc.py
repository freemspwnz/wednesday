"""Tests for ChatScheduleUseCase."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from domain.chat import (
    Chat,
    ChatId,
    ChatNotFoundError,
    ChatProfile,
    ChatSchedule,
    ChatScheduleSet,
    ChatType,
    InactiveState,
    StaleWriteError,
    Weekday,
)
from domain.chat.exceptions import ScheduleLimitExceededError
from domain.kernel.vo import AwareDatetime

from .helpers import dt, make_schedule_uc, mk_chat, owner_actor

# 2026-01-07 is Wednesday.
_WED_NOON = AwareDatetime(datetime(2026, 1, 7, 12, 0, tzinfo=UTC))


def _chat_with_slot(
    *,
    chat_id: int,
    hour: int = 12,
    weekday: Weekday = Weekday.WEDNESDAY,
    timezone: ZoneInfo | None = None,
    active: bool = True,
) -> Chat:
    schedules = ChatScheduleSet(
        timezone=timezone or ZoneInfo("UTC"),
        weekday=weekday,
        schedules=(ChatSchedule(hour, 0),),
    )
    profile = ChatProfile(type=ChatType.PRIVATE, telegram_id=-1000 - chat_id)
    cid = ChatId(value=UUID(int=chat_id))
    if active:
        return Chat.register(id=cid, profile=profile, schedules=schedules, at=_WED_NOON)
    return Chat.restore(
        id=cid,
        profile=profile,
        state=InactiveState(),
        schedules=schedules,
        created_at=_WED_NOON,
        updated_at=_WED_NOON,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_list_due_keeps_matching_active_slot() -> None:
    due = _chat_with_slot(chat_id=1, hour=12)
    inactive = _chat_with_slot(chat_id=2, hour=12, active=False)
    empty = Chat.register(
        id=ChatId(value=UUID(int=3)),
        profile=ChatProfile(type=ChatType.PRIVATE, telegram_id=-1003),
        schedules=ChatScheduleSet(timezone=ZoneInfo("UTC")),
        at=_WED_NOON,
    )
    other_day = _chat_with_slot(chat_id=4, hour=12, weekday=Weekday.FRIDAY)
    other_time = _chat_with_slot(chat_id=5, hour=9)
    moscow_due = _chat_with_slot(
        chat_id=6,
        hour=15,
        timezone=ZoneInfo("Europe/Moscow"),
    )
    repo = AsyncMock()
    repo.list_active_scheduled.return_value = [due, inactive, empty, other_day, other_time, moscow_due]
    uc, uow, cache = make_schedule_uc(repo=repo)

    got = await uc.list_due(at=_WED_NOON)

    assert got == [due, moscow_due]
    repo.list_active_scheduled.assert_awaited_once()
    repo.save.assert_not_awaited()
    cache.chats.set.assert_not_awaited()
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_chat_not_found_does_not_save() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    uc, uow, _cache = make_schedule_uc(repo=repo)
    cid = ChatId(value=UUID(int=99))
    dummy = mk_chat(chat_id=99)

    with pytest.raises(ChatNotFoundError) as ei:
        await uc.clear_schedules(chat_id=cid, actor=owner_actor(dummy), at=dt(11))

    assert ei.value.chat_id == str(cid)
    repo.save.assert_not_awaited()
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_schedule_day_and_timezone_happy_path() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _, _cache = make_schedule_uc(repo=repo)
    london = ZoneInfo("Europe/London")

    await uc.change_schedule_day(
        chat_id=chat.id,
        actor=owner_actor(chat),
        new_weekday=Weekday.FRIDAY,
        at=dt(11),
    )
    await uc.change_schedule_timezone(
        chat_id=chat.id,
        actor=owner_actor(chat),
        timezone=london,
        at=dt(12),
    )

    assert chat.schedules.weekday == Weekday.FRIDAY
    assert chat.schedules.timezone == london
    assert repo.save.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_add_remove_clear_schedules_happy_path() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _, _cache = make_schedule_uc(repo=repo)
    slot = ChatSchedule(9, 30)

    await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=slot, at=dt(11))
    await uc.remove_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=slot, at=dt(12))
    await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=ChatSchedule(10, 0), at=dt(13))
    await uc.clear_schedules(chat_id=chat.id, actor=owner_actor(chat), at=dt(14))

    assert chat.schedules.schedules == ()
    assert repo.save.await_count == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_stale_write_propagates() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _, _cache = make_schedule_uc(repo=repo)

    await uc.change_schedule_day(
        chat_id=chat.id,
        actor=owner_actor(chat),
        new_weekday=Weekday.TUESDAY,
        at=dt(12),
    )

    with pytest.raises(StaleWriteError):
        await uc.change_schedule_day(
            chat_id=chat.id,
            actor=owner_actor(chat),
            new_weekday=Weekday.THURSDAY,
            at=dt(11),
        )

    assert repo.save.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_schedule_limit_exceeded_propagates() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _, _cache = make_schedule_uc(repo=repo)

    await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=ChatSchedule(8, 0), at=dt(11))
    await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=ChatSchedule(9, 0), at=dt(12))
    await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=ChatSchedule(10, 0), at=dt(13))

    with pytest.raises(ScheduleLimitExceededError):
        await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=ChatSchedule(11, 0), at=dt(14))

    assert repo.save.await_count == 3
