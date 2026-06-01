"""Shared factories for presentation telegram tests (not pytest fixtures)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram.types import CallbackQuery, Chat as TgChat, Message, User as TgUser
from dom.user.factories import dt, mk_user

from app.dto import ChatContext, UserContext
from domain.chat import Chat, ChatId, ChatProfile, ChatScheduleSet, ChatType, Weekday
from domain.kernel.vo import AwareDatetime
from domain.user import User, UserRole

_MSG_DATE = datetime(2026, 1, 1, tzinfo=UTC)


def make_message(*, text: str = "/cmd", user_id: int = 1, chat_id: int = 1) -> Message:
    return Message(
        message_id=1,
        date=_MSG_DATE,
        text=text,
        chat=TgChat(id=chat_id, type="private" if chat_id > 0 else "supergroup"),
        from_user=TgUser(id=user_id, is_bot=False, first_name="A"),
    )


def make_callback_query(*, data: str, user_id: int = 1, chat_id: int = 1) -> CallbackQuery:
    message = make_message(chat_id=chat_id, user_id=user_id)
    return CallbackQuery(
        id="cq1",
        from_user=TgUser(id=user_id, is_bot=False, first_name="A"),
        chat_instance="test",
        data=data,
        message=message,
    )


class ScopeCM:
    def __init__(self, scope: object) -> None:
        self._scope = scope

    async def __aenter__(self) -> object:
        return self._scope

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


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
