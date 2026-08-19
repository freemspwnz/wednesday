from functools import cached_property

from app.protocols import CacheRepoRegistry, Logger, RequestScope, UoWFactory
from app.use_cases import (
    ChatManagementUseCase,
    ChatScheduleUseCase,
    ImageCatalogUseCase,
    ImageGenerationUseCase,
    ImageManagementUseCase,
    ImageVoteUseCase,
    UserGenerationUseCase,
    UserLifecycleUseCase,
    UserManagementUseCase,
    UserModerationUseCase,
)
from domain.catalog import ModelCatalog, SubscriptionCatalog
from domain.image import PromptCatalog, PromptModerationPolicy
from infra.network.httpx import ProvidersRegistry
from infra.persistence.yaml import YamlCatalogFactory


class ScopeContainer(RequestScope):
    def __init__(
        self,
        *,
        uow: UoWFactory,
        cache: CacheRepoRegistry,
        catalog: YamlCatalogFactory,
        providers: ProvidersRegistry,
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._cache = cache
        self._catalog = catalog
        self._providers = providers
        self._logger = logger

    @cached_property
    def logger(self) -> Logger:
        return self._logger

    @cached_property
    def models(self) -> ModelCatalog:
        return self._catalog.models

    @cached_property
    def subscriptions(self) -> SubscriptionCatalog:
        return self._catalog.subscriptions

    @cached_property
    def prompts(self) -> PromptCatalog:
        return self._catalog.prompts

    @cached_property
    def user_lifecycle_uc(self) -> UserLifecycleUseCase:
        return UserLifecycleUseCase(
            models=self.models,
            subscriptions=self.subscriptions,
            cache=self._cache.users,
            uow=self._uow(),
            logger=self._logger,
        )

    @cached_property
    def user_management_uc(self) -> UserManagementUseCase:
        return UserManagementUseCase(
            cache=self._cache.users,
            uow=self._uow(),
            logger=self._logger,
        )

    @cached_property
    def user_moderation_uc(self) -> UserModerationUseCase:
        return UserModerationUseCase(
            cache=self._cache.users,
            uow=self._uow(),
            logger=self._logger,
        )

    @cached_property
    def user_generation_uc(self) -> UserGenerationUseCase:
        return UserGenerationUseCase(
            models=self.models,
            subscriptions=self.subscriptions,
            cache=self._cache.users,
            uow=self._uow(),
            logger=self._logger,
        )

    @cached_property
    def chat_management_uc(self) -> ChatManagementUseCase:
        return ChatManagementUseCase(
            cache=self._cache.chats,
            uow=self._uow(),
            logger=self._logger,
        )

    @cached_property
    def chat_schedule_uc(self) -> ChatScheduleUseCase:
        return ChatScheduleUseCase(
            cache=self._cache.chats,
            uow=self._uow(),
            logger=self._logger,
        )

    @cached_property
    def image_catalog_uc(self) -> ImageCatalogUseCase:
        return ImageCatalogUseCase(
            uow=self._uow(),
            logger=self._logger,
        )

    @cached_property
    def image_vote_uc(self) -> ImageVoteUseCase:
        return ImageVoteUseCase(
            uow=self._uow(),
            logger=self._logger,
        )

    @cached_property
    def image_management_uc(self) -> ImageManagementUseCase:
        return ImageManagementUseCase(
            uow=self._uow(),
            logger=self._logger,
        )

    @cached_property
    def image_generation_uc(self) -> ImageGenerationUseCase:
        return ImageGenerationUseCase(
            generators=self._providers,
            prompts=self.prompts,
            policy=PromptModerationPolicy(),
            uow=self._uow(),
            logger=self._logger,
        )
