from dataclasses import dataclass
from datetime import datetime
from typing import Self

from domain.chat import ActiveState, Chat


@dataclass
class ChatContext:
    """Registered chat read-model for handlers and cache (always fully materialized)."""

    id: str
    tg_id: int
    type: str
    is_active: bool
    timezone: str
    weekday: int
    schedules: list[tuple[int, int]]
    created_at: datetime
    updated_at: datetime
    title: str | None = None
    username: str | None = None

    @classmethod
    def from_domain(cls, chat: Chat) -> Self:
        return cls(
            id=str(chat.id),
            tg_id=chat.profile.telegram_id,
            type=str(chat.profile.type),
            title=chat.profile.title,
            username=chat.profile.username,
            is_active=isinstance(chat.state, ActiveState),
            timezone=str(chat.schedules.timezone),
            weekday=int(chat.schedules.weekday),
            schedules=[(slot.hour, slot.minute) for slot in chat.schedules.schedules],
            created_at=chat.created_at.value,
            updated_at=chat.updated_at.value,
        )
