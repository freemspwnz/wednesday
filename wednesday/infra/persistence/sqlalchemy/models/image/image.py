"""ORM: Image catalog aggregate."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ImageORM(Base):
    """Aggregate root: meta, rating, visibility state, prompts, Telegram file id."""

    __tablename__ = "images"
    __table_args__ = (
        CheckConstraint("state IN ('active', 'hidden')", name="ck_images_state"),
        CheckConstraint(
            "hidden_reason IS NULL OR hidden_reason IN ('admin', 'rating')",
            name="ck_images_hidden_reason",
        ),
        CheckConstraint(
            "(state = 'active' AND hidden_reason IS NULL) OR (state = 'hidden' AND hidden_reason IS NOT NULL)",
            name="ck_images_state_reason_coherence",
        ),
        CheckConstraint(
            "prompt_source IN ('user', 'llm', 'fallback')",
            name="ck_images_prompt_source",
        ),
        CheckConstraint("likes >= 0", name="ck_images_likes_nonneg"),
        CheckConstraint("dislikes >= 0", name="ck_images_dislikes_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    author_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    likes: Mapped[int] = mapped_column(Integer, nullable=False)
    dislikes: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    hidden_reason: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    primary_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    enriched_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_source: Mapped[str] = mapped_column(String(16), nullable=False)
    telegram_file_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)

    def __repr__(self) -> str:
        return (
            f"ImageORM(id={self.id!r}, author_id={self.author_id!r}, model={self.model!r}, "
            f"likes={self.likes!r}, dislikes={self.dislikes!r}, state={self.state!r}, "
            f"hidden_reason={self.hidden_reason!r}, prompt_source={self.prompt_source!r})"
        )
