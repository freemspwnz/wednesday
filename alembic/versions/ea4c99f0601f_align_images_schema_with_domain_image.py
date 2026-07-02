"""align_images_schema_with_domain_image

Revision ID: ea4c99f0601f
Revises: fb548c333d1f
Create Date: 2026-07-02 12:03:54.487989

Align images table with domain/image BC:
- hidden_reason: votes -> score
- prompt_source column (user | llm | fallback)
- delete rows with NULL telegram_file_id / primary_prompt
- telegram_file_id NOT NULL
- primary_prompt NOT NULL
- rename image_seen -> image_view (ViewRepo)
- rename status column -> state
- rename user_prompt -> primary_prompt
- rename image_view.seen_at -> shown_at
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ea4c99f0601f"
down_revision: str | None = "fb548c333d1f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "wednesday_schema"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE {SCHEMA}.images
        SET hidden_reason = 'score'
        WHERE hidden_reason = 'votes'
        """
    )

    op.drop_constraint("ck_images_status_reason_coherence", "images", schema=SCHEMA, type_="check")
    op.drop_constraint("ck_images_status", "images", schema=SCHEMA, type_="check")
    op.drop_constraint("ck_images_hidden_reason", "images", schema=SCHEMA, type_="check")
    op.alter_column("images", "status", new_column_name="state", schema=SCHEMA)
    op.create_check_constraint(
        "ck_images_state",
        "images",
        "state IN ('active', 'hidden')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_images_hidden_reason",
        "images",
        "hidden_reason IS NULL OR hidden_reason IN ('admin', 'score')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_images_state_reason_coherence",
        "images",
        "(state = 'active' AND hidden_reason IS NULL) OR (state = 'hidden' AND hidden_reason IS NOT NULL)",
        schema=SCHEMA,
    )

    op.add_column(
        "images",
        sa.Column("prompt_source", sa.String(length=16), server_default="user", nullable=False),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_images_prompt_source",
        "images",
        "prompt_source IN ('user', 'llm', 'fallback')",
        schema=SCHEMA,
    )
    op.alter_column("images", "prompt_source", server_default=None, schema=SCHEMA)

    op.execute(
        f"""
        DELETE FROM {SCHEMA}.images
        WHERE telegram_file_id IS NULL
        """
    )

    op.alter_column(
        "images",
        "telegram_file_id",
        existing_type=sa.String(length=256),
        nullable=False,
        schema=SCHEMA,
    )

    op.alter_column("images", "user_prompt", new_column_name="primary_prompt", schema=SCHEMA)

    op.execute(
        f"""
        DELETE FROM {SCHEMA}.images
        WHERE primary_prompt IS NULL
        """
    )

    op.alter_column(
        "images",
        "primary_prompt",
        existing_type=sa.Text(),
        nullable=False,
        schema=SCHEMA,
    )

    op.rename_table("image_seen", "image_view", schema=SCHEMA)
    op.alter_column("image_view", "seen_at", new_column_name="shown_at", schema=SCHEMA)


def downgrade() -> None:
    op.alter_column("image_view", "shown_at", new_column_name="seen_at", schema=SCHEMA)
    op.rename_table("image_view", "image_seen", schema=SCHEMA)

    op.alter_column(
        "images",
        "primary_prompt",
        existing_type=sa.Text(),
        nullable=True,
        schema=SCHEMA,
    )
    op.alter_column("images", "primary_prompt", new_column_name="user_prompt", schema=SCHEMA)

    op.alter_column(
        "images",
        "telegram_file_id",
        existing_type=sa.String(length=256),
        nullable=True,
        schema=SCHEMA,
    )

    op.drop_constraint("ck_images_prompt_source", "images", schema=SCHEMA, type_="check")
    op.drop_column("images", "prompt_source", schema=SCHEMA)

    op.drop_constraint("ck_images_state_reason_coherence", "images", schema=SCHEMA, type_="check")
    op.drop_constraint("ck_images_hidden_reason", "images", schema=SCHEMA, type_="check")
    op.drop_constraint("ck_images_state", "images", schema=SCHEMA, type_="check")
    op.alter_column("images", "state", new_column_name="status", schema=SCHEMA)
    op.create_check_constraint(
        "ck_images_status",
        "images",
        "status IN ('active', 'hidden')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_images_hidden_reason",
        "images",
        "hidden_reason IS NULL OR hidden_reason IN ('admin', 'votes')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_images_status_reason_coherence",
        "images",
        "(status = 'active' AND hidden_reason IS NULL) OR (status = 'hidden' AND hidden_reason IS NOT NULL)",
        schema=SCHEMA,
    )

    op.execute(
        f"""
        UPDATE {SCHEMA}.images
        SET hidden_reason = 'votes'
        WHERE hidden_reason = 'score'
        """
    )
