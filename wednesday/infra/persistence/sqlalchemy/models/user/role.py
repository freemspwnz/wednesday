from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base
from .user import UserORM


class UserRoleORM(Base):
    """1:1 — текущий UserRole."""

    __tablename__ = "user_roles"
    __table_args__ = (CheckConstraint("role IN (0, 1, 2, 3)", name="ck_user_roles_role"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    user: Mapped[UserORM] = relationship("UserORM", back_populates="role")
