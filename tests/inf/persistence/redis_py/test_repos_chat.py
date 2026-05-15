"""Тесты RedisChatRepo без реального Redis."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infra.persistence.redis.repos.chat import RedisChatRepo
from infra.persistence.redis.snapshots.chat import ChatSnapshot

from .snapshots import chat_snapshot


@pytest.mark.unit
class TestRedisChatRepo:
    @pytest.mark.asyncio
    async def test_get_by_id_miss_uses_expected_key(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value=None)
        repo = RedisChatRepo(client=client, logger=mock_logger)
        assert await repo.get_by_id(42) is None
        client.get.assert_awaited_once_with("ctx:chat:42")

    @pytest.mark.asyncio
    async def test_invalidate_deletes_key(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.delete = AsyncMock()
        repo = RedisChatRepo(client=client, logger=mock_logger)
        await repo.invalidate(7)
        client.delete.assert_awaited_once_with("ctx:chat:7")

    @pytest.mark.asyncio
    async def test_get_by_id_hit_returns_context(self, mock_logger: MagicMock) -> None:
        payload = chat_snapshot(tg_id=55).model_dump_json()
        client = MagicMock()
        client.get = AsyncMock(return_value=payload)
        repo = RedisChatRepo(client=client, logger=mock_logger)
        ctx = await repo.get_by_id(55)
        assert ctx is not None
        assert ctx.tg_id == 55

    @pytest.mark.asyncio
    async def test_get_by_id_validation_error_invalidates(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value="{}")
        client.delete = AsyncMock()
        repo = RedisChatRepo(client=client, logger=mock_logger)
        assert await repo.get_by_id(1) is None
        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_by_id_stale_version_invalidates(self, mock_logger: MagicMock) -> None:
        stale = chat_snapshot(v=999).model_dump_json()
        client = MagicMock()
        client.get = AsyncMock(return_value=stale)
        client.delete = AsyncMock()
        repo = RedisChatRepo(client=client, logger=mock_logger)
        assert await repo.get_by_id(1) is None
        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_by_id_parse_runtime_error_invalidates(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value="{}")
        client.delete = AsyncMock()
        with patch.object(ChatSnapshot, "model_validate_json", side_effect=RuntimeError("boom")):
            repo = RedisChatRepo(client=client, logger=mock_logger)
            assert await repo.get_by_id(1) is None

        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_set_calls_client(self, mock_logger: MagicMock) -> None:
        fake_snap = MagicMock()
        fake_snap.model_dump_json.return_value = '{"stub":true}'
        client = MagicMock()
        client.set = AsyncMock()

        chat = MagicMock()
        chat.profile.telegram_id = 88

        with patch.object(ChatSnapshot, "from_domain", return_value=fake_snap):
            repo = RedisChatRepo(client=client, logger=mock_logger, ttl=timedelta(minutes=5))
            await repo.set(chat)

        client.set.assert_awaited_once()
        call_kw = client.set.await_args.kwargs
        assert call_kw["expire"] == 300
        pos = client.set.await_args.args
        assert pos[0] == "ctx:chat:88"
        assert pos[1] == '{"stub":true}'
