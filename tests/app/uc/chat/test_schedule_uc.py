"""Tests for ChatScheduleUseCase."""

from unittest.mock import AsyncMock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from domain.chat import (
    ChatId,
    ChatNotFoundError,
    ChatSchedule,
    StaleWriteError,
    Weekday,
)
from domain.chat.exceptions import ScheduleLimitExceededError

from .helpers import dt, make_schedule_uc, mk_chat, owner_actor


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
