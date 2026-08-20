"""Shared helpers for chat use-case tests."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID
from zoneinfo import ZoneInfo

from app.use_cases.chat import ChatManagementUseCase, ChatScheduleUseCase
from domain.chat import (
    Chat,
    ChatId,
    ChatMemberRole,
    ChatProfile,
    ChatScheduleSet,
    ChatType,
)
from domain.kernel.vo import AwareDatetime

from ...factories import FakeCacheRegistry, FakeUoW, mk_logger


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, 0, tzinfo=UTC))


def plain_dt(hour: int) -> datetime:
    return dt(hour).value


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


def mk_chat_for_tg(*, tg_id: int, now: AwareDatetime | None = None) -> Chat:
    """Domain chat whose id matches ``ChatId.from_int(tg_id)`` (register/find path)."""
    current = now or dt(12)
    return Chat.register(
        id=ChatId.from_int(tg_id),
        profile=ChatProfile(type=ChatType.GROUP, telegram_id=tg_id, title="T"),
        schedules=chat_schedule_set(),
        at=current,
    )


def owner_kwargs(chat: Chat) -> dict:
    return {
        "actor_id": 1,
        "actor_role": ChatMemberRole.OWNER.value,
        "chat_id": str(chat.id),
    }


def member_kwargs(chat: Chat) -> dict:
    return {
        "actor_id": 3,
        "actor_role": ChatMemberRole.MEMBER.value,
        "chat_id": str(chat.id),
    }


def register_kwargs(
    *,
    tg_id: int = -100,
    type: str = ChatType.GROUP.value,
    title: str | None = "T",
    username: str | None = None,
    at: datetime | None = None,
) -> dict:
    return {
        "tg_id": tg_id,
        "type": type,
        "title": title,
        "username": username,
        "at": at or plain_dt(12),
    }


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
