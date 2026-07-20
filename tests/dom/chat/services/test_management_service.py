"""Tests for ChatManagementService."""

from unittest.mock import AsyncMock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from domain.chat import (
    Chat,
    ChatId,
    ChatManagementService,
    ChatMember,
    ChatMemberId,
    ChatMemberRole,
    ChatNotFoundError,
    ChatProfile,
    ChatScheduleSet,
    ChatType,
    Weekday,
)
from domain.chat.services.utils import chat_id_from_tg
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
async def test_get_or_create_returns_existing() -> None:
    repo = AsyncMock()
    profile = ChatProfile(type=ChatType.PRIVATE, telegram_id=-1001)
    existing = Chat.register(
        id=chat_id_from_tg(profile.telegram_id),
        profile=profile,
        schedules=ChatScheduleSet(timezone=ZoneInfo("UTC")),
        at=dt(10),
    )
    repo.get_by_id.return_value = existing

    result = await ChatManagementService.get_or_create(
        profile=profile,
        repo=repo,
        at=dt(11),
    )

    assert result is existing
    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_or_create_creates_new_entity() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    profile = ChatProfile(
        type=ChatType.GROUP,
        telegram_id=-100123,
        title="Ops",
        username="ops_chat",
    )

    result = await ChatManagementService.get_or_create(
        profile=profile,
        repo=repo,
        at=dt(11),
    )

    assert isinstance(result, Chat)
    assert result.profile.telegram_id == -100123
    assert result.profile.type == ChatType.GROUP
    assert result.id == chat_id_from_tg(-100123)
    assert result.schedules.weekday == Weekday.WEDNESDAY
    repo.save.assert_awaited_once_with(result)


@pytest.mark.unit
def test_id_from_tg_is_deterministic() -> None:
    assert chat_id_from_tg(2) == chat_id_from_tg(2)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_change_profile_persists_via_repo() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    new_profile = ChatProfile(type=ChatType.GROUP, telegram_id=-1001, title="Direct")

    await ChatManagementService.change_profile(
        id=chat.id,
        actor=owner_actor(chat),
        new_profile=new_profile,
        repo=repo,
        at=dt(11),
    )

    repo.save.assert_awaited_once_with(chat)
    assert chat.profile == new_profile


@pytest.mark.unit
@pytest.mark.asyncio
async def test_activate_raises_not_found() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    cid = ChatId(value=UUID(int=99))
    dummy = mk_chat(chat_id=99)

    with pytest.raises(ChatNotFoundError) as ei:
        await ChatManagementService.activate(
            id=cid,
            actor=owner_actor(dummy),
            repo=repo,
            at=dt(11),
        )

    assert ei.value.chat_id == str(cid)
    repo.save.assert_not_awaited()
