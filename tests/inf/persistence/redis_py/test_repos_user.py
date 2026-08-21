"""RedisUserRepo tests without a real Redis."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.exceptions import CacheInvalidDataError
from infra.persistence.redis.codec import dump_user_context, load_user_context
from infra.persistence.redis.repos.user import RedisUserRepo

from .contexts import mk_user_context, user_payload


@pytest.mark.unit
class TestRedisUserRepo:
    @pytest.mark.asyncio
    async def test_get_by_id_miss_uses_expected_key(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value=None)
        repo = RedisUserRepo(client=client, logger=mock_logger)
        assert await repo.get_by_id(42) is None
        client.get.assert_awaited_once_with("ctx:user:42")

    @pytest.mark.asyncio
    async def test_invalidate_deletes_key(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.delete = AsyncMock()
        repo = RedisUserRepo(client=client, logger=mock_logger)
        await repo.invalidate(7)
        client.delete.assert_awaited_once_with("ctx:user:7")

    @pytest.mark.asyncio
    async def test_get_by_id_hit_returns_context(self, mock_logger: MagicMock) -> None:
        payload = user_payload(tg_id=77)
        client = MagicMock()
        client.get = AsyncMock(return_value=payload)
        repo = RedisUserRepo(client=client, logger=mock_logger)
        ctx = await repo.get_by_id(77)
        assert ctx is not None
        assert ctx.tg_id == 77

    @pytest.mark.asyncio
    async def test_get_by_id_validation_error_invalidates(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value="{}")
        client.delete = AsyncMock()
        repo = RedisUserRepo(client=client, logger=mock_logger)
        assert await repo.get_by_id(1) is None
        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_by_id_legacy_v1_invalidates(self, mock_logger: MagicMock) -> None:
        legacy = user_payload(v=1)
        client = MagicMock()
        client.get = AsyncMock(return_value=legacy)
        client.delete = AsyncMock()
        repo = RedisUserRepo(client=client, logger=mock_logger)
        assert await repo.get_by_id(1) is None
        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_by_id_stale_version_invalidates(self, mock_logger: MagicMock) -> None:
        stale = user_payload(v=999)
        client = MagicMock()
        client.get = AsyncMock(return_value=stale)
        client.delete = AsyncMock()
        repo = RedisUserRepo(client=client, logger=mock_logger)
        assert await repo.get_by_id(1) is None
        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_by_id_invalid_payload_invalidates(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value="{")
        client.delete = AsyncMock()
        repo = RedisUserRepo(client=client, logger=mock_logger)
        assert await repo.get_by_id(1) is None
        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_by_id_codec_error_invalidates(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value="{}")
        client.delete = AsyncMock()
        with patch(
            "infra.persistence.redis.repos.user.load_user_context",
            side_effect=CacheInvalidDataError("boom", operation="load_user_context"),
        ):
            repo = RedisUserRepo(client=client, logger=mock_logger)
            assert await repo.get_by_id(1) is None
        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_set_calls_client(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.set = AsyncMock()
        context = mk_user_context(tg_id=33)
        repo = RedisUserRepo(client=client, logger=mock_logger, ttl=timedelta(minutes=5))
        await repo.set(context)

        client.set.assert_awaited_once()
        assert client.set.await_args.args[0] == "ctx:user:33"
        assert client.set.await_args.kwargs["expire"] == 300
        stored = client.set.await_args.args[1]
        assert load_user_context(stored).tg_id == 33
        assert stored == dump_user_context(context)
