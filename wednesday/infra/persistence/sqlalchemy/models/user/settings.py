from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base
from .user import UserORM


class UserSettingsORM(Base):
    """1:1 — selected generation model (vendor / series / model)."""

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    vendor: Mapped[str] = mapped_column(String(64), nullable=False)
    series: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped[UserORM] = relationship("UserORM", back_populates="settings")

    def __repr__(self) -> str:
        return (
            f"UserSettingsORM(user_id={self.user_id!r}, vendor={self.vendor!r}, "
            f"series={self.series!r}, model={self.model!r})"
        )
