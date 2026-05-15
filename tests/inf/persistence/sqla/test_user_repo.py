from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.exceptions import SQLAAggregateMappingError, SQLADataIntegrityError, SQLARepositoryError
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole
from domain.user.vo import UserSubscription
from infra.persistence.sqlalchemy.models import UserORM
from infra.persistence.sqlalchemy.repos import SQLAUserRepo


def _dt(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, 0, tzinfo=UTC)


def _aware(hour: int) -> AwareDatetime:
    return AwareDatetime(_dt(hour))


def mk_user(*, user_id: int = 1, hour: int = 12) -> User:
    now = _aware(hour)
    return User.register(
        id=UserId(UUID(int=user_id)),
        profile=UserProfile(telegram_id=100_000 + user_id, is_bot=False, first_name=NonEmptyStr("Test")),
        role=UserRole.USER,
        subscription=UserSubscription.free(now),
        now=now,
    )


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_save_uses_postgres_on_conflict_for_all_user_tables() -> None:
    session = AsyncMock()
    repo = SQLAUserRepo(session=session)
    user = mk_user(hour=10)

    await repo.save(user)

    assert session.execute.await_count == 5
    sql_texts = [str(call.args[0]) for call in session.execute.await_args_list]
    assert all("ON CONFLICT" in sql for sql in sql_texts)


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_save_wraps_integrity_error() -> None:
    session = AsyncMock()
    session.execute.side_effect = IntegrityError("stmt", {}, Exception("boom"))
    repo = SQLAUserRepo(session=session)
    user = mk_user()

    with pytest.raises(SQLADataIntegrityError):
        await repo.save(user)


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_get_by_id_wraps_mapping_errors() -> None:
    session = AsyncMock()
    orm_user = UserORM(
        id=mk_user().id.value,
        created_at=_dt(10),
        updated_at=_dt(10),
        last_seen_at=_dt(10),
    )
    result = Mock()
    result.scalar_one_or_none.return_value = orm_user
    session.execute.return_value = result
    repo = SQLAUserRepo(session=session)

    with pytest.raises(SQLAAggregateMappingError):
        await repo.get_by_id(mk_user().id)


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_exists_wraps_sqla_error() -> None:
    session = AsyncMock()
    session.execute.side_effect = SQLAlchemyError("db down")
    repo = SQLAUserRepo(session=session)

    with pytest.raises(SQLARepositoryError):
        await repo.exists(mk_user().id)
