from app.dto import UserContext
from app.protocols import CacheRepo, Logger, UoW
from domain.catalog import ModelCatalog, SubscriptionCatalog
from domain.kernel.vo import AwareDatetime
from domain.user import User, UserId, UserProfile, UserRole, UserSettings, UserSubscription
from domain.user.helpers import user_id_from_tg

from .base import UserBaseUseCase


class UserLifecycleUseCase(UserBaseUseCase):
    """User lifecycle use case methods (registration + state expiration)."""

    def __init__(
        self,
        *,
        uow: UoW,
        cache: CacheRepo[UserContext, User],
        models: ModelCatalog,
        subscriptions: SubscriptionCatalog,
        logger: Logger,
    ) -> None:
        super().__init__(uow=uow, cache=cache, logger=logger)
        self._models = models
        self._subscriptions = subscriptions

    async def register(self, *, profile: UserProfile) -> UserContext:
        cached = await self._cache.get_by_id(profile.telegram_id)
        if cached is not None:
            self._logger.debug(
                "Registration cache hit",
                entity="user",
                tg_id=profile.telegram_id,
            )
            return cached

        self._logger.debug(
            "Registration cache miss, loading user",
            entity="user",
            tg_id=profile.telegram_id,
        )
        async with self._uow:
            resolved = await self._get_or_create(profile=profile, at=AwareDatetime.now_utc())

        await self._cache.set(resolved)
        self._logger.debug(
            "Registration user context materialized",
            entity="user",
            tg_id=profile.telegram_id,
        )
        return UserContext.from_domain(resolved)

    async def find_by_tg_id(self, *, tg_id: int) -> UserContext | None:
        """Return existing user context; never creates a new aggregate."""
        cached = await self._cache.get_by_id(tg_id)
        if cached is not None:
            self._logger.debug("User lookup cache hit", tg_id=tg_id)
            return cached

        self._logger.debug("User lookup cache miss", tg_id=tg_id)
        async with self._uow:
            entity = await self._uow.users.get_by_id(user_id_from_tg(tg_id))
        if entity is None:
            return None

        await self._cache.set(entity)
        return UserContext.from_domain(entity)

    async def expire_subscription_if_due(self, *, user_id: UserId, at: AwareDatetime) -> User:
        return await self._run_mutating(
            action="expire_subscription_if_due",
            user_id=user_id,
            runner=lambda: self._expire_subscription_if_due(user_id=user_id, at=at),
        )

    async def mark_seen(self, *, user_id: UserId, at: AwareDatetime) -> User:
        self._log_scenario_start(action="mark_seen", user_id=user_id)
        async with self._uow:
            user = await self._load_user_or_raise(user_id=user_id)
            user.mark_seen_at(at=at)
            await self._uow.users.save(user)
            return user

    async def _get_or_create(self, *, profile: UserProfile, at: AwareDatetime) -> User:
        user_id = user_id_from_tg(profile.telegram_id)
        existing = await self._uow.users.get_by_id(user_id)
        if existing is not None:
            existing.mark_seen_at(at=at)
            await self._uow.users.save(existing)
            return existing

        default_plan = await self._subscriptions.default_plan()
        default_descriptor = await self._models.default_for_tier(default_plan.tier)
        user = User.register(
            id=user_id,
            profile=profile,
            role=UserRole.USER,
            subscription=UserSubscription(
                plan=default_plan,
                started_at=at,
                expires_at=None,
            ),
            settings=UserSettings.from_descriptor(default_descriptor),
            at=at,
        )
        await self._uow.users.save(user)
        return user

    async def _expire_subscription_if_due(self, *, user_id: UserId, at: AwareDatetime) -> User:
        user = await self._load_user_or_raise(user_id=user_id)
        fallback = await self._subscriptions.default_plan()
        user.expire_subscription_if_due(fallback=fallback, at=at)
        await self._uow.users.save(user)
        return user
