"""Unit of Work protocols for managing database transactions."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, runtime_checkable

from domain.chat import ChatRepo
from domain.image import ImageRepo, ImageSeenRepo, ImageVoteRepo
from domain.user import UserRepo
from domain.user.protocols import UsageRepo, ViolationRepo


@runtime_checkable
class UoW(Protocol):
    """Protocol for Unit of Work managing database transactions."""

    async def __aenter__(self) -> UoW:
        """Enter context manager. Begins transaction."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit context manager. Commits or rolls back transaction."""
        ...

    @property
    def users(self) -> UserRepo: ...

    @property
    def chats(self) -> ChatRepo: ...

    @property
    def usage(self) -> UsageRepo: ...

    @property
    def violations(self) -> ViolationRepo: ...

    @property
    def images(self) -> ImageRepo: ...

    @property
    def seen(self) -> ImageSeenRepo: ...

    @property
    def votes(self) -> ImageVoteRepo: ...


@runtime_checkable
class UoWFactory(Protocol):
    """Protocol for factory creating UoW instances."""

    def __call__(self) -> UoW:
        """Create new UoW instance.

        Returns:
            New UoW instance for use in transaction.
        """
        ...

    async def aclose(self) -> None: ...
