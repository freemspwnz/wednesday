"""ORM: агрегат User"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .profile import UserProfileORM
    from .role import UserRoleORM
    from .state import UserStateORM
    from .subscription import UserSubscriptionORM


class UserORM(Base):
    """Корень агрегата: идентичность и временные метки."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    profile: Mapped[UserProfileORM] = relationship(
        "UserProfileORM",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        single_parent=True,
        lazy="joined",
    )
    role: Mapped[UserRoleORM] = relationship(
        "UserRoleORM",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        single_parent=True,
        lazy="joined",
    )
    state: Mapped[UserStateORM] = relationship(
        "UserStateORM",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        single_parent=True,
        lazy="joined",
    )
    subscription: Mapped[UserSubscriptionORM] = relationship(
        "UserSubscriptionORM",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        single_parent=True,
        lazy="joined",
    )

    def __repr__(self) -> str:
        return (
            f"UserORM(id={self.id!r}, created_at={self.created_at!r}, "
            f"updated_at={self.updated_at!r}, last_seen_at={self.last_seen_at!r})"
        )
