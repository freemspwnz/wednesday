from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import SQLADataIntegrityError, SQLARepositoryError, UnexpectedSQLAError
from domain.kernel.vo import AwareDatetime
from domain.user import UserId
from domain.user.policies import ViolationStats
from domain.user.protocols import ViolationRepo

from ...models import UserViolationORM


class SQLAViolationRepo(ViolationRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_violation_stats(self, user_id: UserId) -> ViolationStats:
        try:
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
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to load violation stats.",
                operation="get_violation_stats",
                entity="user_violations",
                entity_id=user_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while loading violation stats.") from exc

    async def record_violation(self, user_id: UserId, at: AwareDatetime) -> None:
        at = AwareDatetime.ensure(at)
        try:
            row = UserViolationORM(
                user_id=user_id.value,
                occurred_at=at.value,
            )
            self._session.add(row)
            await self._session.flush()
        except IntegrityError as exc:
            raise SQLADataIntegrityError(
                "Violation record violated database constraints.",
                operation="record_violation",
                entity="user_violations",
                entity_id=user_id.value,
            ) from exc
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to record violation.",
                operation="record_violation",
                entity="user_violations",
                entity_id=user_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while recording violation.") from exc
