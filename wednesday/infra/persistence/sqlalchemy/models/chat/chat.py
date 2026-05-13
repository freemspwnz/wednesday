"""ORM: агрегат Chat — корень + 1:1 сателлиты + слоты расписания."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .profile import ChatProfileORM
    from .schedule_settings import ChatScheduleSettingsORM
    from .schedule_slots import ChatScheduleSlotORM
    from .state import ChatStateORM


class ChatORM(Base):
    """Корень агрегата: идентичность и updated/created."""

    __tablename__ = "chats"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    profile: Mapped[ChatProfileORM] = relationship(
        "ChatProfileORM",
        back_populates="chat",
        cascade="all, delete-orphan",
        uselist=False,
        single_parent=True,
        lazy="joined",
    )
    state: Mapped[ChatStateORM] = relationship(
        "ChatStateORM",
        back_populates="chat",
        cascade="all, delete-orphan",
        uselist=False,
        single_parent=True,
        lazy="joined",
    )
    schedule_settings: Mapped[ChatScheduleSettingsORM] = relationship(
        "ChatScheduleSettingsORM",
        back_populates="chat",
        cascade="all, delete-orphan",
        uselist=False,
        single_parent=True,
        lazy="joined",
    )
    schedule_slots: Mapped[list[ChatScheduleSlotORM]] = relationship(
        "ChatScheduleSlotORM",
        back_populates="chat",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ChatScheduleSlotORM.id",
    )

    def __repr__(self) -> str:
        return f"ChatORM(id={self.id!r}, created_at={self.created_at!r}, updated_at={self.updated_at!r})"
