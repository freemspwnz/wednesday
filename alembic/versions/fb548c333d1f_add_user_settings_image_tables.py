"""add_user_settings_image_tables

Revision ID: fb548c333d1f
Revises: 8593d284af18
Create Date: 2026-05-30 16:51:12.895795

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "fb548c333d1f"
down_revision: str | None = "8593d284af18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "wednesday_schema"
DEFAULT_VENDOR = "sber"
DEFAULT_SERIES = "gigachat"
DEFAULT_MODEL = "gigachat-2-lite"


def upgrade() -> None:
    op.create_table(
        "images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("hidden_reason", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_prompt", sa.Text(), nullable=True),
        sa.Column("enriched_prompt", sa.Text(), nullable=True),
        sa.Column("telegram_file_id", sa.String(length=256), nullable=True),
        sa.CheckConstraint(
            "(status = 'active' AND hidden_reason IS NULL) OR "
            "(status = 'hidden' AND hidden_reason IS NOT NULL)",
            name="ck_images_status_reason_coherence",
        ),
        sa.CheckConstraint(
            "hidden_reason IS NULL OR hidden_reason IN ('admin', 'votes')",
            name="ck_images_hidden_reason",
        ),
        sa.CheckConstraint("status IN ('active', 'hidden')", name="ck_images_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_file_id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_wednesday_schema_images_author_id"),
        "images",
        ["author_id"],
        unique=False,
        schema=SCHEMA,
    )
    op.create_table(
        "image_seen",
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], [f"{SCHEMA}.chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["image_id"], [f"{SCHEMA}.images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id", "image_id"),
        schema=SCHEMA,
    )
    op.create_table(
        "image_votes",
        sa.Column("image_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("voter_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.CheckConstraint("value IN (-1, 1)", name="ck_image_votes_value"),
        sa.ForeignKeyConstraint(["image_id"], [f"{SCHEMA}.images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("image_id", "voter_id"),
        schema=SCHEMA,
    )
    op.create_table(
        "user_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor", sa.String(length=64), nullable=False),
        sa.Column("series", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        schema=SCHEMA,
    )
    op.execute(
        f"""
        INSERT INTO {SCHEMA}.user_settings (user_id, vendor, series, model)
        SELECT u.id, '{DEFAULT_VENDOR}', '{DEFAULT_SERIES}', '{DEFAULT_MODEL}'
        FROM {SCHEMA}.users u
        WHERE NOT EXISTS (
            SELECT 1 FROM {SCHEMA}.user_settings s WHERE s.user_id = u.id
        )
        """
    )
    op.create_table(
        "user_usage",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_usage_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("daily_usage", sa.Integer(), server_default="0", nullable=False),
        sa.Column("daily_usage_on", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        schema=SCHEMA,
    )
    op.create_table(
        "user_violations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_user_violations_user_id_occurred_at",
        "user_violations",
        ["user_id", "occurred_at"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_user_violations_user_id_occurred_at", table_name="user_violations", schema=SCHEMA)
    op.drop_table("user_violations", schema=SCHEMA)
    op.drop_table("user_usage", schema=SCHEMA)
    op.drop_table("user_settings", schema=SCHEMA)
    op.drop_table("image_votes", schema=SCHEMA)
    op.drop_table("image_seen", schema=SCHEMA)
    op.drop_index(op.f("ix_wednesday_schema_images_author_id"), table_name="images", schema=SCHEMA)
    op.drop_table("images", schema=SCHEMA)
