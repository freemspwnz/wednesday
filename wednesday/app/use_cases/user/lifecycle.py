from app.dto import UserContext
from app.protocols import CacheRepo, Logger, UoW
from domain.catalog import ModelCatalog, SubscriptionCatalog
from domain.kernel.vo import AwareDatetime
from domain.user import User, UserId, UserLifecycleService, UserProfile

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
            resolved = await UserLifecycleService.get_or_create(
                profile=profile,
                repo=self._uow.users,
                models=self._models,
                subscriptions=self._subscriptions,
                at=AwareDatetime.now_utc(),
            )

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
            entity = await UserLifecycleService.get_if_exists(
                tg_id=tg_id,
                repo=self._uow.users,
            )
        if entity is None:
            return None

        await self._cache.set(entity)
        return UserContext.from_domain(entity)

    async def expire_subscription_if_due(self, *, user_id: UserId, at: AwareDatetime) -> User:
        return await self._run_mutating(
            action="expire_subscription_if_due",
            user_id=user_id,
            runner=lambda: UserLifecycleService.expire_subscription_if_due(
                id=user_id,
                repo=self._uow.users,
                subscriptions=self._subscriptions,
                at=at,
            ),
        )

    async def mark_seen(self, *, user_id: UserId, at: AwareDatetime) -> User:
        self._log_scenario_start(action="mark_seen", user_id=user_id)
        async with self._uow:
            return await UserLifecycleService.mark_seen(
                id=user_id,
                repo=self._uow.users,
                at=at,
            )
