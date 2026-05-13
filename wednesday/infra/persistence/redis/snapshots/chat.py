from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from app.dto import ChatContext
from domain.chat import ActiveState, Chat, ChatId, ChatSchedule, ChatType, Weekday
from domain.kernel.vo import AwareDatetime

CHAT_SNAPSHOT_VERSION = 1


class ChatSnapshot(BaseModel):
    v: int = CHAT_SNAPSHOT_VERSION
    id: str
    tg_id: int
    type: str
    title: str | None = None
    username: str | None = None
    is_active: bool
    timezone: str
    weekday: int
    schedules: list[tuple[int, int]]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, chat: Chat) -> "ChatSnapshot":
        return cls(
            id=str(chat.id.value),
            tg_id=chat.profile.telegram_id,
            type=chat.profile.type.value,
            title=chat.profile.title,
            username=chat.profile.username,
            is_active=isinstance(chat.state, ActiveState),
            timezone=str(chat.schedules.timezone),
            weekday=int(chat.schedules.weekday),
            schedules=[(slot.hour, slot.minute) for slot in chat.schedules.schedules],
            created_at=chat.created_at.value,
            updated_at=chat.updated_at.value,
        )

    def to_context(self) -> ChatContext:
        return ChatContext(
            id=ChatId(UUID(self.id)),
            tg_id=self.tg_id,
            type=ChatType(self.type),
            title=self.title,
            username=self.username,
            is_active=self.is_active,
            timezone=ZoneInfo(self.timezone),
            weekday=Weekday(self.weekday),
            schedules=tuple(ChatSchedule(hour=hour, minute=minute) for hour, minute in self.schedules),
            created_at=AwareDatetime(self.created_at),
            updated_at=AwareDatetime(self.updated_at),
        )
