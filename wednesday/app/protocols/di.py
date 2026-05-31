from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Protocol

from domain.catalog import ModelCatalog, SubscriptionCatalog

from .observe import Logger

if TYPE_CHECKING:
    from app.use_cases import (
        ChatCommandsUseCase,
        ImageRandomUseCase,
        ImageVoteUseCase,
        ModelSelectionUseCase,
        RegistrationUseCase,
        UserCommandsUseCase,
    )


class RequestScope(Protocol):
    """Протокол request scope: use case'ы и logger на время обработки update."""

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
    def model_selection_uc(self) -> ModelSelectionUseCase: ...

    @property
    def image_random_uc(self) -> ImageRandomUseCase: ...

    @property
    def image_vote_uc(self) -> ImageVoteUseCase: ...


ScopeFactory = Callable[[], AbstractAsyncContextManager[RequestScope]]
