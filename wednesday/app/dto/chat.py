from dataclasses import dataclass
from zoneinfo import ZoneInfo

from domain.chat import ActiveState, Chat, ChatId, ChatSchedule, ChatType, Weekday
from domain.kernel.vo import AwareDatetime


@dataclass
class ChatContext:
    tg_id: int
    type: ChatType
    id: ChatId | None = None
    title: str | None = None
    username: str | None = None
    is_active: bool = True
    timezone: ZoneInfo | None = None
    weekday: Weekday | None = None
    schedules: tuple[ChatSchedule, ...] = ()
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None

    @classmethod
    def from_domain(cls, chat: Chat) -> "ChatContext":
        return ChatContext(
            tg_id=chat.profile.telegram_id,
            type=chat.profile.type,
            id=chat.id,
            title=chat.profile.title,
            username=chat.profile.username,
            is_active=isinstance(chat.state, ActiveState),
            timezone=chat.schedules.timezone,
            weekday=chat.schedules.weekday,
            schedules=chat.schedules.schedules,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )
