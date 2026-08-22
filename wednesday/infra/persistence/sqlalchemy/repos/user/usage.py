from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.kernel.vo import AwareDatetime
from domain.user import UsageRepo, UsageSnapshot, UsageStats, UserId

from ...models import UserUsageORM
from .._guard import guard_repo


class SQLAUsageRepo(UsageRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _lock_row(self, user_id: UserId, usage_on: date) -> UserUsageORM:
        stmt = select(UserUsageORM).where(UserUsageORM.user_id == user_id.value).with_for_update()
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            return row
        # create baseline row once, then lock it
        await self._session.execute(
            insert(UserUsageORM)
            .values(
                user_id=user_id.value,
                last_usage_at=None,
                daily_usage=0,
                daily_usage_on=usage_on,
            )
            .on_conflict_do_nothing(index_elements=[UserUsageORM.user_id]),
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        return row

    @staticmethod
    def _stats_from_row(row: UserUsageORM, usage_on: date) -> UsageStats:
        last_usage = AwareDatetime.from_datetime(row.last_usage_at) if row.last_usage_at is not None else None
        daily_usage = row.daily_usage if row.daily_usage_on == usage_on else 0
        return UsageStats(last_usage=last_usage, daily_usage=daily_usage)

    async def _load_stats(self, user_id: UserId, at: AwareDatetime, *, lock: bool) -> UsageStats:
        at = AwareDatetime.ensure(at)
        usage_on = at.value.date()
        if lock:
            return self._stats_from_row(await self._lock_row(user_id, usage_on), usage_on)

        stmt = select(UserUsageORM).where(UserUsageORM.user_id == user_id.value)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return UsageStats(last_usage=None, daily_usage=0)
        return self._stats_from_row(row, usage_on)

    async def get_stats(self, user_id: UserId, at: AwareDatetime, lock: bool = False) -> UsageStats:
        return await guard_repo(
            operation="get_stats",
            entity="user_usage",
            entity_id=user_id.value,
            sqlalchemy_message="SQLAlchemy failed to load usage stats.",
            unexpected_message="Unexpected error while loading usage stats.",
            run=lambda: self._load_stats(user_id, at, lock=lock),
        )

    async def _persist_record(self, user_id: UserId, at: AwareDatetime) -> UsageSnapshot:
        usage_on = at.value.date()
        row = await self._lock_row(user_id, usage_on)

        snapshot = UsageSnapshot(
            last_usage=AwareDatetime.from_datetime(row.last_usage_at) if row.last_usage_at else None,
            daily_usage=row.daily_usage if row.daily_usage_on == usage_on else 0,
            daily_usage_on=row.daily_usage_on,
        )

        row.last_usage_at = at.value
        row.daily_usage = snapshot.daily_usage + 1
        row.daily_usage_on = usage_on
        return snapshot

    async def record(self, user_id: UserId, at: AwareDatetime) -> UsageSnapshot:
        return await guard_repo(
            operation="record",
            entity="user_usage",
            entity_id=user_id.value,
            integrity_message="Usage record violated database constraints.",
            sqlalchemy_message="SQLAlchemy failed to record usage.",
            unexpected_message="Unexpected error while recording usage.",
            run=lambda: self._persist_record(user_id, at),
        )

    async def _persist_refund(self, user_id: UserId, snapshot: UsageSnapshot) -> None:
        row = await self._lock_row(user_id, AwareDatetime.now_utc().value.date())
        row.last_usage_at = snapshot.last_usage.value if snapshot.last_usage else None
        row.daily_usage = max(0, snapshot.daily_usage)
        row.daily_usage_on = snapshot.daily_usage_on

    async def refund(self, user_id: UserId, snapshot: UsageSnapshot) -> None:
        await guard_repo(
            operation="refund",
            entity="user_usage",
            entity_id=user_id.value,
            integrity_message="Usage refund violated database constraints.",
            sqlalchemy_message="SQLAlchemy failed to refund usage.",
            unexpected_message="Unexpected error while refunding usage.",
            run=lambda: self._persist_refund(user_id, snapshot),
        )
