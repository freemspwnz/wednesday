"""Shared factories and fakes for app-layer tests."""

from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock, Mock
from uuid import UUID
from zoneinfo import ZoneInfo

from app.dto import ChatContext, UserContext
from domain.chat import Chat, ChatId, ChatProfile, ChatRepo, ChatScheduleSet, ChatType, Weekday
from domain.image import ImageRepo, ViewRepo, VoteRepo
from domain.kernel.vo import AwareDatetime
from domain.user import User, UserRepo, UserRole, ViolationRepo
from domain.user.protocols import UsageRepo
from tests.dom.user.factories import dt, mk_user


def mk_logger() -> Mock:
    log = Mock()
    log.bind.return_value = log
    return log


class FakeCacheRegistry:
    def __init__(self) -> None:
        self.users = AsyncMock()
        self.chats = AsyncMock()


class FakeUoW:
    """Minimal UoW for use-case unit tests: repositories are injected or AsyncMock."""

    def __init__(  # noqa: PLR0913
        self,
        *,
        users: UserRepo | AsyncMock | None = None,
        chats: ChatRepo | AsyncMock | None = None,
        usage: UsageRepo | AsyncMock | None = None,
        violations: ViolationRepo | AsyncMock | None = None,
        images: ImageRepo | AsyncMock | None = None,
        views: ViewRepo | AsyncMock | None = None,
        votes: VoteRepo | AsyncMock | None = None,
    ) -> None:
        self.users = users if users is not None else AsyncMock()
        self.chats = chats if chats is not None else AsyncMock()
        self.usage = usage if usage is not None else AsyncMock()
        self.violations = violations if violations is not None else AsyncMock()
        self.images = images if images is not None else AsyncMock()
        self.views = views if views is not None else AsyncMock()
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


def mk_user_context(
    *,
    user: User | None = None,
    user_id: int = 1,
    role: UserRole = UserRole.USER,
    now: AwareDatetime | None = None,
) -> UserContext:
    entity = user or mk_user(user_id=user_id, role=role, now=now)
    return UserContext.from_domain(entity)


def mk_chat_context(
    *,
    chat: Chat | None = None,
    tg_id: int = -1001,
    chat_type: ChatType = ChatType.SUPERGROUP,
    domain_id: int = 10,
) -> ChatContext:
    if chat is not None:
        return ChatContext.from_domain(chat)
    entity = Chat.register(
        id=ChatId(value=UUID(int=domain_id)),
        profile=ChatProfile(type=chat_type, telegram_id=tg_id, title="Test"),
        schedules=ChatScheduleSet(timezone=ZoneInfo("UTC"), weekday=Weekday.WEDNESDAY),
        at=dt(9),
    )
    return ChatContext.from_domain(entity)
