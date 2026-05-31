"""Общие фабрики и фейки для app-layer тестов."""

from __future__ import annotations

from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock, Mock

from domain.chat import ChatRepo
from domain.image import ImageRepo, ImageSeenRepo, ImageVoteRepo
from domain.user.protocols import UsageRepo, UserRepo, ViolationRepo


def mk_logger() -> Mock:
    log = Mock()
    log.bind.return_value = log
    return log


class FakeCacheRegistry:
    def __init__(self) -> None:
        self.user = AsyncMock()
        self.chat = AsyncMock()


class FakeUoW:
    """Минимальный UoW для unit-тестов use case: все репозитории — переданные или AsyncMock."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        users: UserRepo | AsyncMock | None = None,
        chats: ChatRepo | AsyncMock | None = None,
        usage: UsageRepo | AsyncMock | None = None,
        violations: ViolationRepo | AsyncMock | None = None,
        images: ImageRepo | AsyncMock | None = None,
        seen: ImageSeenRepo | AsyncMock | None = None,
        votes: ImageVoteRepo | AsyncMock | None = None,
    ) -> None:
        self.users = users if users is not None else AsyncMock()
        self.chats = chats if chats is not None else AsyncMock()
        self.usage = usage if usage is not None else AsyncMock()
        self.violations = violations if violations is not None else AsyncMock()
        self.images = images if images is not None else AsyncMock()
        self.seen = seen if seen is not None else AsyncMock()
        self.votes = votes if votes is not None else AsyncMock()
        self.enter_count = 0
        self.exit_count = 0

    async def __aenter__(self) -> Self:
        self.enter_count += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.exit_count += 1
