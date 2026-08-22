from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.kernel.vo import AwareDatetime
from domain.user import UserId, ViolationRepo, ViolationStats

from ...models import UserViolationORM
from .._guard import guard_repo


class SQLAViolationRepo(ViolationRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_violation_stats(self, user_id: UserId) -> ViolationStats:
        async def _run() -> ViolationStats:
            now = AwareDatetime.now_utc().value
            hour_start = now - timedelta(hours=1)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = now - timedelta(days=7)

            uid = user_id.value
            violation = UserViolationORM
            stmt = select(
                func.count().filter(violation.user_id == uid).label("total"),
                func.count().filter(violation.user_id == uid, violation.occurred_at >= hour_start).label("hour"),
                func.count().filter(violation.user_id == uid, violation.occurred_at >= day_start).label("today"),
                func.count().filter(violation.user_id == uid, violation.occurred_at >= week_start).label("week"),
            ).select_from(violation)
            result = await self._session.execute(stmt)
            row = result.one()
            return ViolationStats(
                hour=int(row.hour),
                today=int(row.today),
                week=int(row.week),
                total=int(row.total),
            )

        return await guard_repo(
            operation="get_violation_stats",
            entity="user_violations",
            entity_id=user_id.value,
            sqlalchemy_message="SQLAlchemy failed to load violation stats.",
            unexpected_message="Unexpected error while loading violation stats.",
            run=_run,
        )

    async def record_violation(self, user_id: UserId, at: AwareDatetime) -> None:
        async def _run() -> None:
            row = UserViolationORM(
                user_id=user_id.value,
                occurred_at=at.value,
            )
            self._session.add(row)
            await self._session.flush()

        return await guard_repo(
            operation="record_violation",
            entity="user_violations",
            entity_id=user_id.value,
            integrity_message="Violation record violated database constraints.",
            sqlalchemy_message="SQLAlchemy failed to record violation.",
            unexpected_message="Unexpected error while recording violation.",
            run=_run,
        )
