from functools import cached_property

from app.protocols import CacheRepoRegistry, Logger, RequestScope, UoWFactory
from app.services import ChatCommandService, RegistrationService, UserCommandService
from app.use_cases import ChatCommandsUseCase, RegistrationUseCase, UserCommandsUseCase


class ScopeContainer(RequestScope):
    def __init__(
        self,
        *,
        uow_factory: UoWFactory,
        cache_registry: CacheRepoRegistry,
        logger: Logger,
    ) -> None:
        self._uow_factory = uow_factory
        self._cache_registry = cache_registry
        self._logger = logger

    @cached_property
    def logger(self) -> Logger:
        return self._logger

    @cached_property
    def registration_uc(self) -> RegistrationUseCase:
        return RegistrationUseCase(
            uow=self._uow_factory(),
            reg_service=self._registration_service,
            cache_registry=self._cache_registry,
            logger=self._logger,
        )

    @cached_property
    def user_commands_uc(self) -> UserCommandsUseCase:
        return UserCommandsUseCase(
            uow=self._uow_factory(),
            user_commands=self._user_commands_service,
            logger=self._logger,
        )

    @cached_property
    def chat_commands_uc(self) -> ChatCommandsUseCase:
        return ChatCommandsUseCase(
            uow=self._uow_factory(),
            chat_commands=self._chat_commands_service,
            logger=self._logger,
        )

    @cached_property
    def _registration_service(self) -> RegistrationService:
        return RegistrationService(
            logger=self._logger,
        )

    @cached_property
    def _user_commands_service(self) -> UserCommandService:
        return UserCommandService(
            logger=self._logger,
        )

    @cached_property
    def _chat_commands_service(self) -> ChatCommandService:
        return ChatCommandService(
            logger=self._logger,
        )
