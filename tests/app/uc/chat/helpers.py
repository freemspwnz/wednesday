"""Shared helpers for chat use-case tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID
from zoneinfo import ZoneInfo

from app.use_cases.chat import ChatManagementUseCase, ChatScheduleUseCase
from domain.chat import (
    Chat,
    ChatId,
    ChatMember,
    ChatMemberId,
    ChatMemberRole,
    ChatProfile,
    ChatScheduleSet,
    ChatType,
)
from domain.kernel.vo import AwareDatetime

from ...factories import FakeCacheRegistry, FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, 0, tzinfo=UTC))


def utc_tz() -> ZoneInfo:
    return ZoneInfo("UTC")


def chat_schedule_set() -> ChatScheduleSet:
    return ChatScheduleSet(timezone=utc_tz())


def mk_chat(*, chat_id: int = 1, telegram_id: int = -1001, now: AwareDatetime | None = None) -> Chat:
    current = now or dt(12)
    cid = ChatId(value=UUID(int=chat_id))
    return Chat.register(
        id=cid,
        profile=ChatProfile(type=ChatType.PRIVATE, telegram_id=telegram_id),
        schedules=chat_schedule_set(),
        at=current,
    )


def owner_actor(chat: Chat) -> ChatMember:
    return ChatMember(id=ChatMemberId(1), role=ChatMemberRole.OWNER, chat_id=chat.id)


def member_actor(chat: Chat) -> ChatMember:
    return ChatMember(id=ChatMemberId(3), role=ChatMemberRole.MEMBER, chat_id=chat.id)


def make_management_uc(
    *,
    repo: AsyncMock,
    logger: Mock | None = None,
) -> tuple[ChatManagementUseCase, FakeUoW, FakeCacheRegistry]:
    log = logger or mk_logger()
    uow = FakeUoW(chats=repo)
    cache = FakeCacheRegistry()
    uc = ChatManagementUseCase(uow=uow, cache=cache.chats, logger=log)
    return uc, uow, cache


def make_schedule_uc(*, repo: AsyncMock) -> tuple[ChatScheduleUseCase, FakeUoW, FakeCacheRegistry]:
    log = mk_logger()
    uow = FakeUoW(chats=repo)
    cache = FakeCacheRegistry()
    uc = ChatScheduleUseCase(uow=uow, cache=cache.chats, logger=log)
    return uc, uow, cache
