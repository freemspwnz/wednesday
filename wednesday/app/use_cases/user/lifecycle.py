from datetime import datetime
from uuid import UUID

from app.dto import UserContext
from app.protocols import CacheRepo, Logger, UoW
from domain.catalog import ModelCatalog, SubscriptionCatalog
from domain.kernel.vo import AwareDatetime, NonEmptyStr
from domain.user import User, UserId, UserProfile, UserRole, UserSettings, UserSubscription

from .base import UserBaseUseCase


class UserLifecycleUseCase(UserBaseUseCase):
    """User lifecycle use case methods (registration + state expiration)."""

    def __init__(
        self,
        *,
        uow: UoW,
        cache: CacheRepo[UserContext],
        models: ModelCatalog,
        subscriptions: SubscriptionCatalog,
        logger: Logger,
    ) -> None:
        super().__init__(uow=uow, cache=cache, logger=logger)
        self._models = models
        self._subscriptions = subscriptions

    async def register(  # noqa: PLR0913
        self,
        *,
        tg_id: int,
        is_bot: bool,
        first_name: str,
        last_name: str | None,
        username: str | None,
        language_code: str | None,
        has_tg_premium: bool | None,
        at: datetime,
    ) -> UserContext:
        cached = await self._cache.get_by_id(tg_id)
        if cached is not None:
            self._logger.debug(
                "Registration cache hit",
                entity="user",
                tg_id=tg_id,
            )
            return cached

        self._logger.debug(
            "Registration cache miss, loading user",
            entity="user",
            tg_id=tg_id,
        )
        async with self._uow:
            resolved = await self._get_or_create(
                tg_id=tg_id,
                is_bot=is_bot,
                first_name=first_name,
                last_name=last_name,
                username=username,
                language_code=language_code,
                has_tg_premium=has_tg_premium,
                at=AwareDatetime.from_datetime(at),
            )

        ctx = UserContext.from_domain(resolved)
        await self._cache.set(ctx)
        self._logger.debug(
            "Registration user context materialized",
            entity="user",
            tg_id=tg_id,
        )
        return ctx

    async def find_by_tg_id(self, *, tg_id: int) -> UserContext | None:
        """Return existing user context; never creates a new aggregate."""
        cached = await self._cache.get_by_id(tg_id)
        if cached is not None:
            self._logger.debug("User lookup cache hit", tg_id=tg_id)
            return cached

        self._logger.debug("User lookup cache miss", tg_id=tg_id)
        async with self._uow:
            user = await self._uow.users.get_by_id(UserId.from_int(tg_id))
        if user is None:
            return None

        ctx = UserContext.from_domain(user)
        await self._cache.set(ctx)
        return ctx

    async def expire_subscription_if_due(self, *, user_id: str, at: datetime) -> UserContext:
        return await self._run_mutating(
            action="expire_subscription_if_due",
            user_id=user_id,
            runner=lambda: self._expire_subscription_if_due(
                user_id=UserId(UUID(user_id)),
                at=AwareDatetime.from_datetime(at),
            ),
        )

    async def mark_seen(self, *, user_id: str, at: datetime) -> UserContext:
        self._log_scenario_start(action="mark_seen", user_id=user_id)
        async with self._uow:
            user = await self._load_user_or_raise(user_id=UserId(UUID(user_id)))
            user.mark_seen_at(at=AwareDatetime.from_datetime(at))
            await self._uow.users.save(user)
            return UserContext.from_domain(user)

    async def _get_or_create(  # noqa: PLR0913
        self,
        *,
        tg_id: int,
        is_bot: bool,
        first_name: str,
        last_name: str | None,
        username: str | None,
        language_code: str | None,
        has_tg_premium: bool | None,
        at: AwareDatetime,
    ) -> User:
        user_id = UserId.from_int(tg_id)
        existing = await self._uow.users.get_by_id(user_id)
        if existing is not None:
            existing.mark_seen_at(at=at)
            await self._uow.users.save(existing)
            return existing

        default_plan = await self._subscriptions.default_plan()
        default_descriptor = await self._models.default_for_tier(default_plan.tier)
        profile = UserProfile(
            telegram_id=tg_id,
            is_bot=is_bot,
            first_name=NonEmptyStr(first_name),
            last_name=NonEmptyStr(last_name) if last_name is not None else None,
            username=username,
            language_code=language_code,
            has_tg_premium=has_tg_premium,
        )
        subscription = UserSubscription(
            plan=default_plan,
            started_at=at,
            expires_at=None,
        )
        user = User.register(
            id=user_id,
            profile=profile,
            role=UserRole.USER,
            subscription=subscription,
            settings=UserSettings.from_descriptor(default_descriptor),
            at=at,
        )
        await self._uow.users.save(user)
        self._logger.info("User registered", tg_id=profile.telegram_id)
        return user

    async def _expire_subscription_if_due(self, *, user_id: UserId, at: AwareDatetime) -> User:
        user = await self._load_user_or_raise(user_id=user_id)
        fallback = await self._subscriptions.default_plan()
        user.expire_subscription_if_due(fallback=fallback, at=at)
        await self._uow.users.save(user)
        return user
