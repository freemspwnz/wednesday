from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING, Protocol

from .observe import Logger

if TYPE_CHECKING:
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


class RequestScope(Protocol):
    """Request scope protocol: use cases and logger for the lifetime of one update handling."""

    @property
    def logger(self) -> Logger: ...

    @property
    def user_lifecycle_uc(self) -> UserLifecycleUseCase: ...

    @property
    def user_management_uc(self) -> UserManagementUseCase: ...

    @property
    def user_moderation_uc(self) -> UserModerationUseCase: ...

    @property
    def user_generation_uc(self) -> UserGenerationUseCase: ...

    @property
    def chat_management_uc(self) -> ChatManagementUseCase: ...

    @property
    def chat_schedule_uc(self) -> ChatScheduleUseCase: ...

    @property
    def image_catalog_uc(self) -> ImageCatalogUseCase: ...

    @property
    def image_vote_uc(self) -> ImageVoteUseCase: ...

    @property
    def image_management_uc(self) -> ImageManagementUseCase: ...

    @property
    def image_generation_uc(self) -> ImageGenerationUseCase: ...


ScopeFactory = Callable[[], AbstractAsyncContextManager[RequestScope]]
