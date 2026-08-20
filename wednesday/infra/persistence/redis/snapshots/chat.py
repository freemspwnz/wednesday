from datetime import datetime
from typing import Self

from pydantic import BaseModel

from app.dto import ChatContext

CHAT_SNAPSHOT_VERSION = 2


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
    def from_context(cls, context: ChatContext) -> Self:
        return cls(
            id=context.id,
            tg_id=context.tg_id,
            type=context.type,
            title=context.title,
            username=context.username,
            is_active=context.is_active,
            timezone=context.timezone,
            weekday=context.weekday,
            schedules=context.schedules,
            created_at=context.created_at,
            updated_at=context.updated_at,
        )

    def to_context(self) -> ChatContext:
        return ChatContext(
            id=self.id,
            tg_id=self.tg_id,
            type=self.type,
            title=self.title,
            username=self.username,
            is_active=self.is_active,
            timezone=self.timezone,
            weekday=self.weekday,
            schedules=self.schedules,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
