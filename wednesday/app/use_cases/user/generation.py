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
