from functools import cached_property

from app.protocols import CacheRepoRegistry, Logger, RequestScope, UoWFactory
from app.use_cases import (
    ChatManagementUseCase,
    ChatScheduleUseCase,
    ImageCommandsUseCase,
    UserGenerationUseCase,
    UserLifecycleUseCase,
    UserManagementUseCase,
    UserModerationUseCase,
)
from domain.catalog import ModelCatalog, SubscriptionCatalog
from domain.image import PromptCatalog
from infra.persistence.yaml import YamlCatalogFactory


class ScopeContainer(RequestScope):
    def __init__(
        self,
        *,
        uow_factory: UoWFactory,
        cache: CacheRepoRegistry,
        catalog: YamlCatalogFactory,
        logger: Logger,
    ) -> None:
        self._uow_factory = uow_factory
        self._cache = cache
        self._catalog = catalog
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
            uow=self._uow_factory(),
            cache=self._cache.users,
            models=self.models,
            subscriptions=self.subscriptions,
            logger=self._logger,
        )

    @cached_property
    def user_management_uc(self) -> UserManagementUseCase:
        return UserManagementUseCase(
            uow=self._uow_factory(),
            cache=self._cache.users,
            logger=self._logger,
        )

    @cached_property
    def user_moderation_uc(self) -> UserModerationUseCase:
        return UserModerationUseCase(
            uow=self._uow_factory(),
            cache=self._cache.users,
            logger=self._logger,
        )

    @cached_property
    def user_generation_uc(self) -> UserGenerationUseCase:
        return UserGenerationUseCase(
            uow=self._uow_factory(),
            cache=self._cache.users,
            models=self.models,
            subscriptions=self.subscriptions,
            logger=self._logger,
        )

    @cached_property
    def chat_management_uc(self) -> ChatManagementUseCase:
        return ChatManagementUseCase(
            uow=self._uow_factory(),
            cache=self._cache.chats,
            logger=self._logger,
        )

    @cached_property
    def chat_schedule_uc(self) -> ChatScheduleUseCase:
        return ChatScheduleUseCase(
            uow=self._uow_factory(),
            cache=self._cache.chats,
            logger=self._logger,
        )

    @cached_property
    def image_commands_uc(self) -> ImageCommandsUseCase:
        return ImageCommandsUseCase(
            uow=self._uow_factory(),
            logger=self._logger,
        )
