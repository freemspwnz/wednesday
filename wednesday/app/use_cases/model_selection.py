from __future__ import annotations

from app.protocols import CacheRepoRegistry, Logger, UoW
from domain.catalog import Model, ModelCatalog, SubscriptionCatalog
from domain.kernel.vo import AwareDatetime
from domain.user import ModelSelectionService, User, UserId


class ModelSelectionUseCase:
    """Смена модели пользователя в транзакции UoW с обновлением Redis-кэша."""

    def __init__(
        self,
        *,
        uow: UoW,
        cache_registry: CacheRepoRegistry,
        model_catalog: ModelCatalog,
        subscription_catalog: SubscriptionCatalog,
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._cache_registry = cache_registry
        self._model_catalog = model_catalog
        self._subscription_catalog = subscription_catalog
        self._logger = logger.bind(module=self.__class__.__name__)

    async def select_model(
        self,
        *,
        user_id: UserId,
        model: Model,
        at: AwareDatetime,
    ) -> User:
        self._logger.debug(
            "Model selection scenario started",
            user_id=str(user_id),
            model=str(model),
        )
        async with self._uow:
            user = await ModelSelectionService.select_model(
                user_id=user_id,
                model=model,
                user_repo=self._uow.users,
                model_catalog=self._model_catalog,
                sub_catalog=self._subscription_catalog,
                at=at,
            )
        await self._cache_registry.user.set(user)
        self._logger.debug(
            "User cache snapshot refreshed after model selection",
            tg_id=user.profile.telegram_id,
            model=str(user.settings.model),
        )
        return user
