from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class VoteORM(Base):
    """User vote on an image (-1 or +1)."""

    __tablename__ = "image_votes"
    __table_args__ = (CheckConstraint("value IN (-1, 1)", name="ck_image_votes_value"),)

    image_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("images.id", ondelete="CASCADE"),
        primary_key=True,
    )
    voter_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"VoteORM(image_id={self.image_id!r}, voter_id={self.voter_id!r}, value={self.value!r})"
