from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.exceptions import SQLAAggregateMappingError, SQLADataIntegrityError, SQLARepositoryError
from domain.catalog import Model, Series, Vendor
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole
from domain.user.vo import UserSettings, UserSubscription
from infra.persistence.sqlalchemy.models import (
    UserORM,
    UserProfileORM,
    UserRoleORM,
    UserSettingsORM,
    UserStateORM,
    UserSubscriptionORM,
)
from infra.persistence.sqlalchemy.repos import SQLAUserRepo
from tests.dom.catalog.plans import FREE_PLAN


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
        subscription=UserSubscription(plan=FREE_PLAN, started_at=now, expires_at=None),
        settings=UserSettings(
            vendor=Vendor.parse("sber"),
            series=Series.parse("gigachat"),
            model=Model.parse("gigachat-2-lite"),
        ),
        at=now,
    )


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_save_uses_postgres_on_conflict_for_all_user_tables() -> None:
    session = AsyncMock()
    repo = SQLAUserRepo(session=session)
    user = mk_user(hour=10)

    await repo.save(user)

    assert session.execute.await_count == 6
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
async def test_get_by_id_maps_settings_roundtrip() -> None:
    user = mk_user(hour=10)
    orm_user = UserORM(
        id=user.id.value,
        created_at=_dt(10),
        updated_at=_dt(10),
        last_seen_at=_dt(10),
    )
    orm_user.profile = UserProfileORM(
        user_id=user.id.value,
        telegram_id=user.profile.telegram_id,
        is_bot=False,
        first_name=str(user.profile.first_name),
    )
    orm_user.role = UserRoleORM(user_id=user.id.value, role=int(user.role))
    orm_user.state = UserStateORM(user_id=user.id.value, banned_until=None)
    orm_user.subscription = UserSubscriptionORM(
        user_id=user.id.value,
        tier=int(user.subscription.plan.tier),
        daily_limit=user.subscription.plan.daily_limit,
        cooldown_minutes=user.subscription.plan.cooldown_minutes,
        started_at=user.subscription.started_at.value,
        expires_at=None,
    )
    orm_user.settings = UserSettingsORM(
        user_id=user.id.value,
        vendor=str(user.settings.vendor),
        series=str(user.settings.series),
        model=str(user.settings.model),
    )
    session = AsyncMock()
    result = Mock()
    result.scalar_one_or_none.return_value = orm_user
    session.execute.return_value = result
    repo = SQLAUserRepo(session=session)

    loaded = await repo.get_by_id(user.id)

    assert loaded is not None
    assert str(loaded.settings.vendor) == "sber"
    assert str(loaded.settings.series) == "gigachat"
    assert str(loaded.settings.model) == "gigachat-2-lite"


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_exists_wraps_sqla_error() -> None:
    session = AsyncMock()
    session.execute.side_effect = SQLAlchemyError("db down")
    repo = SQLAUserRepo(session=session)

    with pytest.raises(SQLARepositoryError):
        await repo.exists(mk_user().id)
