from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class UserViolationORM(Base):
    """Single moderation violation row for rolling ViolationStats windows."""

    __tablename__ = "user_violations"
    __table_args__ = (Index("ix_user_violations_user_id_occurred_at", "user_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"UserViolationORM(id={self.id!r}, user_id={self.user_id!r}, occurred_at={self.occurred_at!r})"
