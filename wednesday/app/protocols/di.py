from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Protocol

from domain.catalog import ModelCatalog, SubscriptionCatalog
from domain.image import PromptCatalog

from .observe import Logger

if TYPE_CHECKING:
    from app.use_cases import (
        ChatCommandsUseCase,
        ImageCommandsUseCase,
        RegistrationUseCase,
        UserCommandsUseCase,
    )


class RequestScope(Protocol):
    """Request scope protocol: use cases and logger for the lifetime of one update handling."""

    @property
    def logger(self) -> Logger: ...

    @property
    def models(self) -> ModelCatalog: ...

    @property
    def subscriptions(self) -> SubscriptionCatalog: ...

    @property
    def prompts(self) -> PromptCatalog: ...

    @property
    def user_commands_uc(self) -> UserCommandsUseCase: ...

    @property
    def chat_commands_uc(self) -> ChatCommandsUseCase: ...

    @property
    def image_commands_uc(self) -> ImageCommandsUseCase: ...

    @property
    def registration_uc(self) -> RegistrationUseCase: ...


ScopeFactory = Callable[[], AbstractAsyncContextManager[RequestScope]]
