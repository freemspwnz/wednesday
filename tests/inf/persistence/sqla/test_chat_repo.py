from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.exc import IntegrityError

from app.exceptions import SQLAAggregateMappingError, SQLADataIntegrityError
from domain.chat import (
    Chat,
    ChatId,
    ChatMember,
    ChatMemberId,
    ChatMemberRole,
    ChatProfile,
    ChatSchedule,
    ChatScheduleSet,
    ChatType,
)
from domain.kernel.vo import AwareDatetime
from infra.persistence.sqlalchemy.models import ChatORM
from infra.persistence.sqlalchemy.repos import SQLAChatRepo


def _dt(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, 0, tzinfo=UTC)


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(_dt(hour))


def mk_chat(*, chat_id: int = 1, telegram_id: int = -1001, hour: int = 12) -> Chat:
    return Chat.register(
        id=ChatId(value=UUID(int=chat_id)),
        profile=ChatProfile(type=ChatType.PRIVATE, telegram_id=telegram_id),
        schedules=ChatScheduleSet(timezone=ZoneInfo("UTC")),
        at=dt(hour),
    )


def owner(*, chat: Chat) -> ChatMember:
    return ChatMember(id=ChatMemberId(1), role=ChatMemberRole.OWNER, chat_id=chat.id)


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_save_uses_postgres_on_conflict_for_chat_tables_and_slots() -> None:
    session = AsyncMock()
    repo = SQLAChatRepo(session=session)
    chat = mk_chat(hour=10)
    chat.add_schedule(actor=owner(chat=chat), schedule=ChatSchedule(hour=9, minute=30), at=dt(11))

    await repo.save(chat)

    sql_texts = [str(call.args[0]) for call in session.execute.await_args_list]
    assert any("INSERT INTO wednesday_schema.chats" in sql for sql in sql_texts)
    assert any("ON CONFLICT" in sql for sql in sql_texts)
    assert any("chat_schedule_slots" in sql for sql in sql_texts)


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_save_wraps_integrity_error() -> None:
    session = AsyncMock()
    session.execute.side_effect = IntegrityError("stmt", {}, Exception("boom"))
    repo = SQLAChatRepo(session=session)

    with pytest.raises(SQLADataIntegrityError):
        await repo.save(mk_chat())


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_get_by_id_wraps_mapping_errors() -> None:
    session = AsyncMock()
    orm_chat = ChatORM(
        id=mk_chat().id.value,
        created_at=_dt(10),
        updated_at=_dt(10),
    )
    result = Mock()
    result.scalar_one_or_none.return_value = orm_chat
    session.execute.return_value = result
    repo = SQLAChatRepo(session=session)

    with pytest.raises(SQLAAggregateMappingError):
        await repo.get_by_id(mk_chat().id)
