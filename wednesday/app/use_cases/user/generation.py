from app.dto import UserContext
from app.protocols import CacheRepo, Logger, UoW
from domain.catalog import Model, ModelCatalog, SubscriptionCatalog
from domain.kernel.vo import AwareDatetime
from domain.user import User, UserGenerationService, UserId

from .base import UserBaseUseCase


class UserGenerationUseCase(UserBaseUseCase):
    """User generation use case methods."""

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

    async def select_model(
        self,
        *,
        user_id: UserId,
        model: Model,
        at: AwareDatetime,
    ) -> User:
        return await self._run_mutating(
            action="select_model",
            user_id=user_id,
            runner=lambda: UserGenerationService.select_model(
                id=user_id,
                model=model,
                repo=self._uow.users,
                models=self._models,
                subs=self._subscriptions,
                at=at,
            ),
        )

    async def assert_allowed(self, *, user_id: UserId, at: AwareDatetime) -> None:
        """Check ban/limits without consuming a generation slot."""
        self._log_scenario_start(action="assert_allowed", user_id=user_id)
        async with self._uow:
            await UserGenerationService.assert_allowed(
                id=user_id,
                repo=self._uow.users,
                usage=self._uow.usage,
                catalog=self._subscriptions,
                at=at,
            )

    async def record_usage(self, *, user_id: UserId, at: AwareDatetime) -> None:
        """Consume one generation slot after a successful render/send."""
        self._log_scenario_start(action="record_usage", user_id=user_id)
        async with self._uow:
            await UserGenerationService.record_usage(
                id=user_id,
                usage=self._uow.usage,
                at=at,
            )
