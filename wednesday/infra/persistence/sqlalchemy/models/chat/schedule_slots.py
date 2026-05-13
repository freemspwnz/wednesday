"""1:N — слоты ChatSchedule (hour, minute); timezone/weekday в chat_schedule_settings."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, SmallInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base
from .chat import ChatORM


class ChatScheduleSlotORM(Base):
    __tablename__ = "chat_schedule_slots"
    __table_args__ = (
        UniqueConstraint("chat_id", "hour", "minute", name="uq_chat_schedule_slot_time"),
        CheckConstraint("hour BETWEEN 0 AND 23", name="ck_chat_schedule_slots_hour"),
        CheckConstraint("minute BETWEEN 0 AND 59", name="ck_chat_schedule_slots_minute"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    minute: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    chat: Mapped[ChatORM] = relationship("ChatORM", back_populates="schedule_slots")

    def __repr__(self) -> str:
        return (
            f"ChatScheduleSlotORM(id={self.id!r}, chat_id={self.chat_id!r}, hour={self.hour!r}, minute={self.minute!r})"
        )
