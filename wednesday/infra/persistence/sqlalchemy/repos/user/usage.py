from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import SQLADataIntegrityError, SQLARepositoryError, UnexpectedSQLAError
from domain.kernel.vo import AwareDatetime
from domain.user import UserId
from domain.user.policies import UsageStats
from domain.user.protocols import UsageRepo

from ...models import UserUsageORM


class SQLAUsageRepo(UsageRepo):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_usage_stats(self, user_id: UserId) -> UsageStats:
        try:
            stmt = select(UserUsageORM).where(UserUsageORM.user_id == user_id.value)
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return UsageStats(last_usage=None, daily_usage=0)

            today = AwareDatetime.now_utc().value.date()
            last_usage = AwareDatetime.from_datetime(row.last_usage_at) if row.last_usage_at is not None else None
            if row.daily_usage_on != today:
                return UsageStats(last_usage=last_usage, daily_usage=0)
            return UsageStats(last_usage=last_usage, daily_usage=row.daily_usage)
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to load usage stats.",
                operation="get_usage_stats",
                entity="user_usage",
                entity_id=user_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while loading usage stats.") from exc

    async def record_usage(self, user_id: UserId, at: AwareDatetime) -> None:
        at = AwareDatetime.ensure(at)
        usage_on = at.value.date()
        try:
            stmt = select(UserUsageORM).where(UserUsageORM.user_id == user_id.value)
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                daily_usage = 1
            elif row.daily_usage_on == usage_on:
                daily_usage = row.daily_usage + 1
            else:
                daily_usage = 1

            await self._session.execute(
                insert(UserUsageORM)
                .values(
                    user_id=user_id.value,
                    last_usage_at=at.value,
                    daily_usage=daily_usage,
                    daily_usage_on=usage_on,
                )
                .on_conflict_do_update(
                    index_elements=[UserUsageORM.user_id],
                    set_={
                        "last_usage_at": at.value,
                        "daily_usage": daily_usage,
                        "daily_usage_on": usage_on,
                    },
                )
            )
        except IntegrityError as exc:
            raise SQLADataIntegrityError(
                "Usage record violated database constraints.",
                operation="record_usage",
                entity="user_usage",
                entity_id=user_id.value,
            ) from exc
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to record usage.",
                operation="record_usage",
                entity="user_usage",
                entity_id=user_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while recording usage.") from exc
