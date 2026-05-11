"""Тесты ChatCommandService и ChatCommandsUseCase."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from app.exceptions import ChatNotFoundError
from app.services.chat_commands_srv import ChatCommandService
from app.use_cases.chat_commands_uc import ChatCommandsUseCase
from domain.chat import (
    ActiveState,
    Chat,
    ChatId,
    ChatMember,
    ChatMemberId,
    ChatMemberRole,
    ChatProfile,
    ChatSchedule,
    ChatScheduleSet,
    ChatType,
    ManagementAccessDeniedError,
    StaleWriteError,
    Weekday,
)
from domain.chat.exceptions import InvalidStateTransitionError, ScheduleLimitExceededError
from domain.kernel.vo import AwareDatetime


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


def _logger() -> Mock:
    log = Mock()
    log.bind.return_value = log
    return log


@pytest.mark.unit
@pytest.mark.asyncio
async def test_service_change_profile_persists_via_repo() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    srv = ChatCommandService(logger=_logger())
    new_profile = ChatProfile(type=ChatType.GROUP, telegram_id=-1001, title="Direct")

    await srv.change_profile(
        repo=repo,
        chat_id=chat.id,
        actor=owner_actor(chat),
        new_profile=new_profile,
        at=dt(11),
    )

    repo.save.assert_awaited_once_with(chat)


class _FakeUoW:
    def __init__(self, chats_repo: AsyncMock) -> None:
        self.chats = chats_repo
        self.users = AsyncMock()
        self.enter_count = 0
        self.exit_count = 0

    async def __aenter__(self) -> _FakeUoW:
        self.enter_count += 1
        return self

    async def __aexit__(self, *_args: object) -> None:
        self.exit_count += 1


def _make_uc(*, repo: AsyncMock) -> tuple[ChatCommandsUseCase, _FakeUoW]:
    log = _logger()
    uow = _FakeUoW(repo)
    uc = ChatCommandsUseCase(
        uow=uow,
        chat_commands=ChatCommandService(logger=log),
        logger=log,
    )
    return uc, uow


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_profile_happy_path_persists_and_closes_uow() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, uow = _make_uc(repo=repo)
    new_profile = ChatProfile(type=ChatType.GROUP, telegram_id=-1001, title="Ops")

    got = await uc.change_profile(
        chat_id=chat.id,
        actor=owner_actor(chat),
        new_profile=new_profile,
        at=dt(11),
    )

    assert got.profile == new_profile
    repo.get_by_id.assert_awaited_once_with(chat.id)
    repo.save.assert_awaited_once_with(chat)
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_chat_not_found_does_not_save() -> None:
    repo = AsyncMock()
    repo.get_by_id.return_value = None
    uc, uow = _make_uc(repo=repo)
    cid = ChatId(value=UUID(int=99))
    dummy = mk_chat(chat_id=99)

    with pytest.raises(ChatNotFoundError) as ei:
        await uc.clear_schedules(chat_id=cid, actor=owner_actor(dummy), at=dt(11))

    assert ei.value.chat_id == cid
    repo.save.assert_not_awaited()
    assert uow.enter_count == uow.exit_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_management_access_denied_propagates_and_skips_save() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _ = _make_uc(repo=repo)
    new_profile = ChatProfile(type=ChatType.GROUP, telegram_id=-1001, title="X")

    with pytest.raises(ManagementAccessDeniedError):
        await uc.change_profile(
            chat_id=chat.id,
            actor=member_actor(chat),
            new_profile=new_profile,
            at=dt(11),
        )

    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_schedule_day_and_timezone_happy_path() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _ = _make_uc(repo=repo)
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
    uc, _ = _make_uc(repo=repo)
    slot = ChatSchedule(9, 30)

    await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=slot, at=dt(11))
    await uc.remove_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=slot, at=dt(12))
    await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=ChatSchedule(10, 0), at=dt(13))
    await uc.clear_schedules(chat_id=chat.id, actor=owner_actor(chat), at=dt(14))

    assert chat.schedules.schedules == ()
    assert repo.save.await_count == 4


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_deactivate_and_activate_happy_path() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _ = _make_uc(repo=repo)

    await uc.deactivate(chat_id=chat.id, actor=owner_actor(chat), at=dt(11))
    await uc.activate(chat_id=chat.id, actor=owner_actor(chat), at=dt(12))

    assert isinstance(chat.state, ActiveState)
    assert repo.save.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_stale_write_propagates() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _ = _make_uc(repo=repo)

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
async def test_uc_activate_when_already_active_propagates() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _ = _make_uc(repo=repo)

    with pytest.raises(InvalidStateTransitionError):
        await uc.activate(chat_id=chat.id, actor=owner_actor(chat), at=dt(11))

    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_schedule_limit_exceeded_propagates() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _ = _make_uc(repo=repo)

    await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=ChatSchedule(8, 0), at=dt(11))
    await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=ChatSchedule(9, 0), at=dt(12))
    await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=ChatSchedule(10, 0), at=dt(13))

    with pytest.raises(ScheduleLimitExceededError):
        await uc.add_schedule(chat_id=chat.id, actor=owner_actor(chat), schedule=ChatSchedule(11, 0), at=dt(14))

    assert repo.save.await_count == 3
