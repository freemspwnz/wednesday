from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from domain.chat import (
    Chat,
    ChatId,
    ChatMember,
    ChatMemberId,
    ChatMemberRole,
    ChatProfile,
    ChatScheduleSet,
    ChatType,
    System,
)
from domain.kernel.vo import AwareDatetime


def dt(hour: int) -> AwareDatetime:
    return AwareDatetime(datetime(2026, 1, 1, hour, 0, 0, tzinfo=UTC))


def utc_tz() -> ZoneInfo:
    return ZoneInfo("UTC")


def default_schedules() -> ChatScheduleSet:
    return ChatScheduleSet(timezone=utc_tz())


def private_profile(telegram_id: int = -1001) -> ChatProfile:
    return ChatProfile(type=ChatType.PRIVATE, telegram_id=telegram_id)


def default_domain_chat_id() -> ChatId:
    """Совпадает с дефолтным `mk_chat(chat_id=1)`."""
    return ChatId(value=UUID(int=1))


def mk_chat(
    *,
    chat_id: int = 1,
    telegram_id: int = -1001,
    now: AwareDatetime | None = None,
) -> Chat:
    current = now or dt(12)
    return Chat.register(
        id=ChatId(value=UUID(int=chat_id)),
        profile=private_profile(telegram_id=telegram_id),
        schedules=default_schedules(),
        at=current,
    )


def owner(member_id: int = 1, *, chat_id: ChatId | None = None) -> ChatMember:
    ch = chat_id if chat_id is not None else default_domain_chat_id()
    return ChatMember(id=ChatMemberId(member_id), role=ChatMemberRole.OWNER, chat_id=ch)


def admin(member_id: int = 2, *, chat_id: ChatId | None = None) -> ChatMember:
    ch = chat_id if chat_id is not None else default_domain_chat_id()
    return ChatMember(id=ChatMemberId(member_id), role=ChatMemberRole.ADMIN, chat_id=ch)


def member(member_id: int = 3, *, chat_id: ChatId | None = None) -> ChatMember:
    ch = chat_id if chat_id is not None else default_domain_chat_id()
    return ChatMember(id=ChatMemberId(member_id), role=ChatMemberRole.MEMBER, chat_id=ch)


def system() -> System:
    return System()
