from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Protocol

from .observe import Logger

if TYPE_CHECKING:
    from app.use_cases import ChatCommandsUseCase, RegistrationUseCase, UserCommandsUseCase


class RequestScope(Protocol):
    """Протокол request scope: use case'ы и logger на время обработки update."""

    @property
    def logger(self) -> Logger: ...

    @property
    def registration_uc(self) -> RegistrationUseCase: ...

    @property
    def user_commands_uc(self) -> UserCommandsUseCase: ...

    @property
    def chat_commands_uc(self) -> ChatCommandsUseCase: ...


ScopeFactory = Callable[[], AbstractAsyncContextManager[RequestScope]]
