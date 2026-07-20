"""Tests for ChatScheduleService."""

from unittest.mock import AsyncMock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from domain.chat import (
    Chat,
    ChatId,
    ChatMember,
    ChatMemberId,
    ChatMemberRole,
    ChatNotFoundError,
    ChatProfile,
    ChatSchedule,
    ChatScheduleService,
    ChatScheduleSet,
    ChatType,
    Weekday,
)
from domain.kernel.vo import AwareDatetime
from tests.dom.chat.factories import dt


def mk_chat(*, chat_id: int = 1, now: AwareDatetime | None = None) -> Chat:
    current = now or dt(12)
    return Chat.register(
        id=ChatId(value=UUID(int=chat_id)),
        profile=ChatProfile(type=ChatType.PRIVATE, telegram_id=-1001),
        schedules=ChatScheduleSet(timezone=ZoneInfo("UTC")),
        at=current,
    )


def owner_actor(chat: Chat) -> ChatMember:
    return ChatMember(id=ChatMemberId(1), role=ChatMemberRole.OWNER, chat_id=chat.id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_change_schedule_day_persists_via_repo() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat

    await ChatScheduleService.change_schedule_day(
        id=chat.id,
        actor=owner_actor(chat),
        new_weekday=Weekday.FRIDAY,
        repo=repo,
        at=dt(11),
    )

    repo.save.assert_awaited_once_with(chat)
    assert chat.schedules.weekday == Weekday.FRIDAY


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clear_schedules_raises_not_found() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    cid = ChatId(value=UUID(int=99))
    dummy = mk_chat(chat_id=99)

    with pytest.raises(ChatNotFoundError) as ei:
        await ChatScheduleService.clear_schedules(
            id=cid,
            actor=owner_actor(dummy),
            repo=repo,
            at=dt(11),
        )

    assert ei.value.chat_id == str(cid)
    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_and_remove_schedule() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    slot = ChatSchedule(9, 30)

    await ChatScheduleService.add_schedule(
        id=chat.id,
        actor=owner_actor(chat),
        schedule=slot,
        repo=repo,
        at=dt(11),
    )
    await ChatScheduleService.remove_schedule(
        id=chat.id,
        actor=owner_actor(chat),
        schedule=slot,
        repo=repo,
        at=dt(12),
    )

    assert chat.schedules.schedules == ()
    assert repo.save.await_count == 2
