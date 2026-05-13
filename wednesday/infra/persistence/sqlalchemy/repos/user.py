from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import (
    SQLAAggregateMappingError,
    SQLADataIntegrityError,
    SQLARepositoryError,
    UnexpectedSQLAError,
)
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import (
    ActiveState,
    BannedState,
    SubscriptionPlan,
    SubscriptionTier,
    User,
    UserId,
    UserProfile,
    UserRepo,
    UserRole,
    UserSubscription,
)

from ..models import UserORM, UserProfileORM, UserRoleORM, UserStateORM, UserSubscriptionORM


class SQLAUserRepo(UserRepo):
    """Репозиторий пользователей на базе SQLAlchemy AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UserId) -> User | None:
        try:
            stmt = select(UserORM).where(UserORM.id == user_id.value)
            result = await self._session.execute(stmt)
            orm_user = result.scalar_one_or_none()
            if orm_user is None:
                return None
            return _user_from_orm(orm_user)
        except ValueError as exc:
            raise SQLAAggregateMappingError(
                "Failed to map ORM user aggregate.",
                operation="get_by_id",
                entity="user",
                entity_id=user_id.value,
            ) from exc
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to load user aggregate.",
                operation="get_by_id",
                entity="user",
                entity_id=user_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while reading user aggregate.") from exc

    async def save(self, user: User) -> None:
        try:
            await self._session.execute(
                insert(UserORM)
                .values(
                    id=user.id.value,
                    created_at=user.created_at.value,
                    updated_at=user.updated_at.value,
                    last_seen_at=user.last_seen_at.value,
                )
                .on_conflict_do_update(
                    index_elements=[UserORM.id],
                    set_={
                        "updated_at": user.updated_at.value,
                        "last_seen_at": user.last_seen_at.value,
                    },
                )
            )

            await self._session.execute(
                insert(UserProfileORM)
                .values(
                    user_id=user.id.value,
                    telegram_id=user.profile.telegram_id,
                    is_bot=user.profile.is_bot,
                    first_name=str(user.profile.first_name),
                    last_name=str(user.profile.last_name) if user.profile.last_name is not None else None,
                    username=user.profile.username,
                    language_code=user.profile.language_code,
                    has_tg_premium=user.profile.has_tg_premium,
                )
                .on_conflict_do_update(
                    index_elements=[UserProfileORM.user_id],
                    set_={
                        "telegram_id": user.profile.telegram_id,
                        "is_bot": user.profile.is_bot,
                        "first_name": str(user.profile.first_name),
                        "last_name": str(user.profile.last_name) if user.profile.last_name is not None else None,
                        "username": user.profile.username,
                        "language_code": user.profile.language_code,
                        "has_tg_premium": user.profile.has_tg_premium,
                    },
                )
            )

            await self._session.execute(
                insert(UserRoleORM)
                .values(
                    user_id=user.id.value,
                    role=int(user.role),
                )
                .on_conflict_do_update(
                    index_elements=[UserRoleORM.user_id],
                    set_={"role": int(user.role)},
                )
            )

            banned_until = user.state.until.value if isinstance(user.state, BannedState) else None
            await self._session.execute(
                insert(UserStateORM)
                .values(
                    user_id=user.id.value,
                    banned_until=banned_until,
                )
                .on_conflict_do_update(
                    index_elements=[UserStateORM.user_id],
                    set_={"banned_until": banned_until},
                )
            )

            expires_at = user.subscription.expires_at.value if user.subscription.expires_at is not None else None
            await self._session.execute(
                insert(UserSubscriptionORM)
                .values(
                    user_id=user.id.value,
                    tier=int(user.subscription.plan.tier),
                    daily_limit=user.subscription.plan.daily_limit,
                    cooldown_minutes=user.subscription.plan.cooldown_minutes,
                    started_at=user.subscription.started_at.value,
                    expires_at=expires_at,
                )
                .on_conflict_do_update(
                    index_elements=[UserSubscriptionORM.user_id],
                    set_={
                        "tier": int(user.subscription.plan.tier),
                        "daily_limit": user.subscription.plan.daily_limit,
                        "cooldown_minutes": user.subscription.plan.cooldown_minutes,
                        "started_at": user.subscription.started_at.value,
                        "expires_at": expires_at,
                    },
                )
            )
        except IntegrityError as exc:
            raise SQLADataIntegrityError(
                "User save violated database constraints.",
                operation="save",
                entity="user",
                entity_id=user.id.value,
            ) from exc
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to persist user aggregate.",
                operation="save",
                entity="user",
                entity_id=user.id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while saving user aggregate.") from exc

    async def exists(self, user_id: UserId) -> bool:
        try:
            stmt = select(exists().where(UserORM.id == user_id.value))
            result = await self._session.execute(stmt)
            return bool(result.scalar_one())
        except SQLAlchemyError as exc:
            raise SQLARepositoryError(
                "SQLAlchemy failed to check user existence.",
                operation="exists",
                entity="user",
                entity_id=user_id.value,
            ) from exc
        except Exception as exc:
            raise UnexpectedSQLAError("Unexpected error while checking user existence.") from exc


def _user_from_orm(orm: UserORM) -> User:
    if orm.profile is None or orm.role is None or orm.state is None or orm.subscription is None:
        raise ValueError(f"Incomplete user aggregate loaded for user_id={orm.id}")

    state = (
        ActiveState()
        if orm.state.banned_until is None
        else BannedState(until=AwareDatetime.from_datetime(orm.state.banned_until))
    )
    plan = SubscriptionPlan(
        tier=SubscriptionTier(orm.subscription.tier),
        daily_limit=orm.subscription.daily_limit,
        cooldown_minutes=orm.subscription.cooldown_minutes,
    )
    subscription = UserSubscription(
        plan=plan,
        started_at=AwareDatetime.from_datetime(orm.subscription.started_at),
        expires_at=(
            AwareDatetime.from_datetime(orm.subscription.expires_at)
            if orm.subscription.expires_at is not None
            else None
        ),
    )
    profile = UserProfile(
        telegram_id=orm.profile.telegram_id,
        is_bot=orm.profile.is_bot,
        first_name=NonEmptyStr(orm.profile.first_name),
        last_name=NonEmptyStr(orm.profile.last_name) if orm.profile.last_name is not None else None,
        username=orm.profile.username,
        language_code=orm.profile.language_code,
        has_tg_premium=orm.profile.has_tg_premium,
    )
    return User.restore(
        id=UserId(orm.id),
        profile=profile,
        role=UserRole(orm.role.role),
        state=state,
        subscription=subscription,
        created_at=AwareDatetime.from_datetime(orm.created_at),
        updated_at=AwareDatetime.from_datetime(orm.updated_at),
        last_seen_at=AwareDatetime.from_datetime(orm.last_seen_at),
    )
