from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Protocol

from domain.catalog import ModelCatalog, SubscriptionCatalog

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
    def registration_uc(self) -> RegistrationUseCase: ...

    @property
    def model_catalog(self) -> ModelCatalog: ...

    @property
    def subscription_catalog(self) -> SubscriptionCatalog: ...

    @property
    def user_commands_uc(self) -> UserCommandsUseCase: ...

    @property
    def chat_commands_uc(self) -> ChatCommandsUseCase: ...

    @property
    def image_commands_uc(self) -> ImageCommandsUseCase: ...


ScopeFactory = Callable[[], AbstractAsyncContextManager[RequestScope]]
