from functools import cached_property

from app.protocols import CacheRepoRegistry, Logger, RequestScope, UoWFactory
from app.services import ChatCommandService, ImageCommandService, RegistrationService, UserCommandService
from app.use_cases import (
    ChatCommandsUseCase,
    ImageCommandsUseCase,
    RegistrationUseCase,
    UserCommandsUseCase,
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
    def registration_uc(self) -> RegistrationUseCase:
        return RegistrationUseCase(
            uow=self._uow_factory(),
            service=self._registration_srv,
            cache=self._cache,
            logger=self._logger,
        )

    @cached_property
    def user_commands_uc(self) -> UserCommandsUseCase:
        return UserCommandsUseCase(
            uow=self._uow_factory(),
            service=self._user_commands_srv,
            cache=self._cache.users,
            models=self.models,
            subscriptions=self.subscriptions,
            logger=self._logger,
        )

    @cached_property
    def chat_commands_uc(self) -> ChatCommandsUseCase:
        return ChatCommandsUseCase(
            uow=self._uow_factory(),
            service=self._chat_commands_srv,
            cache=self._cache.chats,
            logger=self._logger,
        )

    @cached_property
    def image_commands_uc(self) -> ImageCommandsUseCase:
        return ImageCommandsUseCase(
            uow=self._uow_factory(),
            service=self._image_commands_srv,
            logger=self._logger,
        )

    @cached_property
    def _registration_srv(self) -> RegistrationService:
        return RegistrationService(
            models=self.models,
            subscriptions=self.subscriptions,
            logger=self._logger,
        )

    @cached_property
    def _user_commands_srv(self) -> UserCommandService:
        return UserCommandService(
            subscriptions=self.subscriptions,
            logger=self._logger,
        )

    @cached_property
    def _chat_commands_srv(self) -> ChatCommandService:
        return ChatCommandService(
            logger=self._logger,
        )

    @cached_property
    def _image_commands_srv(self) -> ImageCommandService:
        return ImageCommandService(
            logger=self._logger,
        )
