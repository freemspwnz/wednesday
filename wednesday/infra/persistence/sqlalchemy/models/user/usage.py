import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class UserUsageORM(Base):
    """1:1 — per-user generation usage counter (limits / cooldown)."""

    __tablename__ = "user_usage"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_usage_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    daily_usage: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    daily_usage_on: Mapped[date] = mapped_column(Date, nullable=False)

    def __repr__(self) -> str:
        return (
            f"UserUsageORM(user_id={self.user_id!r}, daily_usage={self.daily_usage!r}, "
            f"daily_usage_on={self.daily_usage_on!r})"
        )
