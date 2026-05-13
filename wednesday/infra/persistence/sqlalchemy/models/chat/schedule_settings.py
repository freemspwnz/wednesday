"""1:1 — timezone + weekday из доменного ChatScheduleSet."""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base
from .chat import ChatORM


class ChatScheduleSettingsORM(Base):
    __tablename__ = "chat_schedule_settings"
    __table_args__ = (CheckConstraint("weekday BETWEEN 1 AND 7", name="ck_chat_schedule_settings_weekday"),)

    chat_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        primary_key=True,
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    chat: Mapped[ChatORM] = relationship("ChatORM", back_populates="schedule_settings")
