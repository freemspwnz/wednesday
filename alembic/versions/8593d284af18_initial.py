"""initial

Revision ID: 8593d284af18
Revises:
Create Date: 2026-05-21 12:57:18.835667

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8593d284af18"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "wednesday_schema"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "chats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_wednesday_schema_chats_updated_at"),
        "chats",
        ["updated_at"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_wednesday_schema_users_last_seen_at"),
        "users",
        ["last_seen_at"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "chat_profiles",
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], [f"{SCHEMA}.chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_wednesday_schema_chat_profiles_telegram_id"),
        "chat_profiles",
        ["telegram_id"],
        unique=True,
        schema=SCHEMA,
    )

    op.create_table(
        "chat_states",
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], [f"{SCHEMA}.chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id"),
        schema=SCHEMA,
    )

    op.create_table(
        "chat_schedule_settings",
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 1 AND 7", name="ck_chat_schedule_settings_weekday"),
        sa.ForeignKeyConstraint(["chat_id"], [f"{SCHEMA}.chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id"),
        schema=SCHEMA,
    )

    op.create_table(
        "chat_schedule_slots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hour", sa.SmallInteger(), nullable=False),
        sa.Column("minute", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("hour BETWEEN 0 AND 23", name="ck_chat_schedule_slots_hour"),
        sa.CheckConstraint("minute BETWEEN 0 AND 59", name="ck_chat_schedule_slots_minute"),
        sa.ForeignKeyConstraint(["chat_id"], [f"{SCHEMA}.chats.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "hour", "minute", name="uq_chat_schedule_slot_time"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_wednesday_schema_chat_schedule_slots_chat_id"),
        "chat_schedule_slots",
        ["chat_id"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "user_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("is_bot", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("language_code", sa.String(length=10), nullable=True),
        sa.Column("has_tg_premium", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_wednesday_schema_user_profiles_telegram_id"),
        "user_profiles",
        ["telegram_id"],
        unique=True,
        schema=SCHEMA,
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("role IN (0, 1, 2, 3)", name="ck_user_roles_role"),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        schema=SCHEMA,
    )

    op.create_table(
        "user_states",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("banned_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        schema=SCHEMA,
    )
    op.create_index(
        op.f("ix_wednesday_schema_user_states_banned_until"),
        "user_states",
        ["banned_until"],
        unique=False,
        schema=SCHEMA,
    )

    op.create_table(
        "user_subscriptions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tier", sa.SmallInteger(), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=False),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("tier >= 0", name="ck_user_subscriptions_tier_non_negative"),
        sa.CheckConstraint("daily_limit >= 0", name="ck_user_subscriptions_daily_limit_non_negative"),
        sa.CheckConstraint("cooldown_minutes >= 0", name="ck_user_subscriptions_cooldown_non_negative"),
        sa.CheckConstraint(
            "expires_at IS NULL OR started_at < expires_at",
            name="ck_user_subscriptions_time_order",
        ),
        sa.ForeignKeyConstraint(["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("user_subscriptions", schema=SCHEMA)
    op.drop_table("user_states", schema=SCHEMA)
    op.drop_table("user_roles", schema=SCHEMA)
    op.drop_table("user_profiles", schema=SCHEMA)
    op.drop_table("chat_schedule_slots", schema=SCHEMA)
    op.drop_table("chat_schedule_settings", schema=SCHEMA)
    op.drop_table("chat_states", schema=SCHEMA)
    op.drop_table("chat_profiles", schema=SCHEMA)
    op.drop_table("users", schema=SCHEMA)
    op.drop_table("chats", schema=SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
