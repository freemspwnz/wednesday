from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, SmallInteger
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base
from .user import UserORM


class UserSubscriptionORM(Base):
    __tablename__ = "user_subscriptions"
    __table_args__ = (
        CheckConstraint("tier >= 0", name="ck_user_subscriptions_tier_non_negative"),
        CheckConstraint("daily_limit >= 0", name="ck_user_subscriptions_daily_limit_non_negative"),
        CheckConstraint("cooldown_minutes >= 0", name="ck_user_subscriptions_cooldown_non_negative"),
        CheckConstraint(
            "expires_at IS NULL OR started_at < expires_at",
            name="ck_user_subscriptions_time_order",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[UserORM] = relationship("UserORM", back_populates="subscription")

    def __repr__(self) -> str:
        return (
            f"UserSubscriptionORM(user_id={self.user_id!r}, tier={self.tier!r}, "
            f"daily_limit={self.daily_limit!r}, cooldown_minutes={self.cooldown_minutes!r}, "
            f"expires_at={self.expires_at!r})"
        )
