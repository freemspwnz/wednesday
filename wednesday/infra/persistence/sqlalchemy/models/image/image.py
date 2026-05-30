"""ORM: Image catalog aggregate."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ImageORM(Base):
    """Aggregate root: meta, score, status, prompts, Telegram file id."""

    __tablename__ = "images"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'hidden')", name="ck_images_status"),
        CheckConstraint(
            "hidden_reason IS NULL OR hidden_reason IN ('admin', 'votes')",
            name="ck_images_hidden_reason",
        ),
        CheckConstraint(
            "(status = 'active' AND hidden_reason IS NULL) OR (status = 'hidden' AND hidden_reason IS NOT NULL)",
            name="ck_images_status_reason_coherence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    author_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    hidden_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    enriched_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)

    def __repr__(self) -> str:
        return (
            f"ImageORM(id={self.id!r}, author_id={self.author_id!r}, model={self.model!r}, "
            f"score={self.score!r}, status={self.status!r}, hidden_reason={self.hidden_reason!r})"
        )
