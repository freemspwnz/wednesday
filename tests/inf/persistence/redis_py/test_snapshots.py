"""Тесты Pydantic-снимков Redis (JSON ↔ DTO)."""

from __future__ import annotations

import pytest

from infra.persistence.redis.snapshots.chat import ChatSnapshot
from infra.persistence.redis.snapshots.user import UserSnapshot

from .snapshots import chat_snapshot, user_snapshot


@pytest.mark.unit
class TestUserSnapshot:
    def test_json_roundtrip_and_to_context(self) -> None:
        snap = user_snapshot()
        restored = UserSnapshot.model_validate_json(snap.model_dump_json())
        assert restored.tg_id == snap.tg_id
        ctx = restored.to_context()
        assert ctx.tg_id == snap.tg_id
        assert ctx.id is not None
        assert str(ctx.id.value) == snap.id


@pytest.mark.unit
class TestChatSnapshot:
    def test_json_roundtrip_and_to_context(self) -> None:
        snap = chat_snapshot()
        restored = ChatSnapshot.model_validate_json(snap.model_dump_json())
        assert restored.tg_id == snap.tg_id
        ctx = restored.to_context()
        assert ctx.tg_id == snap.tg_id
        assert ctx.id is not None
        assert str(ctx.id.value) == snap.id
