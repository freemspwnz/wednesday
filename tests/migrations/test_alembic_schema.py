"""Тесты Alembic: ревизии и соответствие ORM."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from infra.persistence.sqlalchemy.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = REPO_ROOT / "alembic" / "versions"
INITIAL_REVISION = VERSIONS_DIR / "8593d284af18_initial.py"
IMAGE_REVISION = VERSIONS_DIR / "fb548c333d1f_add_user_settings_image_tables.py"
LATEST_HEAD = "fb548c333d1f"

INITIAL_TABLES = {
    "chats",
    "users",
    "chat_profiles",
    "chat_states",
    "chat_schedule_settings",
    "chat_schedule_slots",
    "user_profiles",
    "user_roles",
    "user_states",
    "user_subscriptions",
}

NEW_TABLES = {
    "images",
    "image_seen",
    "image_votes",
    "user_settings",
    "user_usage",
    "user_violations",
}

EXPECTED_TABLES = INITIAL_TABLES | NEW_TABLES


def _tables_created_in(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    created: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "create_table" and isinstance(func.value, ast.Name):
            if func.value.id == "op" and node.args:
                created.add(ast.literal_eval(node.args[0]))
    return created


@pytest.mark.unit
def test_single_head_revision() -> None:
    cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == [LATEST_HEAD]


@pytest.mark.unit
def test_orm_tables_match_expected() -> None:
    orm_tables = {key.split(".", 1)[1] for key in Base.metadata.tables}
    assert orm_tables == EXPECTED_TABLES


@pytest.mark.unit
def test_migrations_create_all_orm_tables() -> None:
    created: set[str] = set()
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        created |= _tables_created_in(path)
    assert created == EXPECTED_TABLES


@pytest.mark.unit
def test_initial_migration_creates_base_tables_only() -> None:
    assert _tables_created_in(INITIAL_REVISION) == INITIAL_TABLES


@pytest.mark.unit
def test_image_migration_creates_extension_tables() -> None:
    assert _tables_created_in(IMAGE_REVISION) == NEW_TABLES


@pytest.mark.unit
def test_image_migration_backfills_user_settings() -> None:
    source = IMAGE_REVISION.read_text(encoding="utf-8")
    assert "INSERT INTO" in source
    assert "user_settings" in source
    assert "gigachat-2-lite" in source
