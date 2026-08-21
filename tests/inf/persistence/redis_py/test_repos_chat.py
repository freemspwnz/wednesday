"""RedisChatRepo tests without a real Redis."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import CacheInvalidDataError
from infra.persistence.redis.codec import dump_chat_context, load_chat_context
from infra.persistence.redis.repos.chat import RedisChatRepo

from .contexts import chat_payload, mk_chat_context


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
        payload = chat_payload(tg_id=55)
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
        stale = chat_payload(v=999)
        client = MagicMock()
        client.get = AsyncMock(return_value=stale)
        client.delete = AsyncMock()
        repo = RedisChatRepo(client=client, logger=mock_logger)
        assert await repo.get_by_id(1) is None
        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_by_id_invalid_payload_invalidates(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value="{")
        client.delete = AsyncMock()
        repo = RedisChatRepo(client=client, logger=mock_logger)
        assert await repo.get_by_id(1) is None
        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_by_id_codec_error_invalidates(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value="{}")
        client.delete = AsyncMock()
        with patch(
            "infra.persistence.redis.repos.chat.load_chat_context",
            side_effect=CacheInvalidDataError("boom", operation="load_chat_context"),
        ):
            repo = RedisChatRepo(client=client, logger=mock_logger)
            assert await repo.get_by_id(1) is None
        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_set_calls_client(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.set = AsyncMock()
        context = mk_chat_context(tg_id=88)
        repo = RedisChatRepo(client=client, logger=mock_logger, ttl=timedelta(minutes=5))
        await repo.set(context)

        client.set.assert_awaited_once()
        call_kw = client.set.await_args.kwargs
        assert call_kw["expire"] == 300
        pos = client.set.await_args.args
        assert pos[0] == "ctx:chat:88"
        assert load_chat_context(pos[1]).tg_id == 88
        assert pos[1] == dump_chat_context(context)
