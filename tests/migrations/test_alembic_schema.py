"""Тесты Alembic: ревизии и соответствие ORM."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from infra.persistence.sqlalchemy.models import Base

REPO_ROOT = Path(__file__).resolve().parents[2]
INITIAL_REVISION = REPO_ROOT / "alembic" / "versions" / "8593d284af18_initial.py"

EXPECTED_TABLES = {
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


@pytest.mark.unit
def test_single_head_revision() -> None:
    cfg = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["8593d284af18"]


@pytest.mark.unit
def test_orm_tables_covered_by_initial_migration() -> None:
    orm_tables = {key.split(".", 1)[1] for key in Base.metadata.tables}
    assert orm_tables == EXPECTED_TABLES

    source = INITIAL_REVISION.read_text(encoding="utf-8")
    tree = ast.parse(source)
    created: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "create_table" and isinstance(func.value, ast.Name):
            if func.value.id == "op" and node.args:
                created.add(ast.literal_eval(node.args[0]))

    assert created == EXPECTED_TABLES
