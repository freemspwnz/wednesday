from dataclasses import dataclass
from zoneinfo import ZoneInfo

from domain.chat import ActiveState, Chat, ChatId, ChatSchedule, ChatType, Weekday
from domain.kernel.vo import AwareDatetime


@dataclass
class ChatContext:
    """Registered chat read-model for handlers and cache (always fully materialized)."""

    id: ChatId
    tg_id: int
    type: ChatType
    is_active: bool
    timezone: ZoneInfo
    weekday: Weekday
    schedules: tuple[ChatSchedule, ...]
    created_at: AwareDatetime
    updated_at: AwareDatetime
    title: str | None = None
    username: str | None = None

    @classmethod
    def from_domain(cls, chat: Chat) -> "ChatContext":
        return ChatContext(
            id=chat.id,
            tg_id=chat.profile.telegram_id,
            type=chat.profile.type,
            title=chat.profile.title,
            username=chat.profile.username,
            is_active=isinstance(chat.state, ActiveState),
            timezone=chat.schedules.timezone,
            weekday=chat.schedules.weekday,
            schedules=chat.schedules.schedules,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )
