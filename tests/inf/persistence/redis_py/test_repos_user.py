"""Тесты RedisUserRepo без реального Redis."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infra.persistence.redis.repos.user import RedisUserRepo
from infra.persistence.redis.snapshots.user import UserSnapshot

from .snapshots import user_snapshot


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
        payload = user_snapshot(tg_id=77).model_dump_json()
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
    async def test_get_by_id_stale_version_invalidates(self, mock_logger: MagicMock) -> None:
        stale = user_snapshot(v=999).model_dump_json()
        client = MagicMock()
        client.get = AsyncMock(return_value=stale)
        client.delete = AsyncMock()
        repo = RedisUserRepo(client=client, logger=mock_logger)
        assert await repo.get_by_id(1) is None
        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_get_by_id_parse_runtime_error_invalidates(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value="{}")
        client.delete = AsyncMock()
        with patch.object(UserSnapshot, "model_validate_json", side_effect=RuntimeError("boom")):
            repo = RedisUserRepo(client=client, logger=mock_logger)
            assert await repo.get_by_id(1) is None

        client.delete.assert_awaited()

    @pytest.mark.asyncio
    async def test_set_calls_client(self, mock_logger: MagicMock) -> None:
        fake_snap = MagicMock()
        fake_snap.model_dump_json.return_value = '{"stub":true}'
        client = MagicMock()
        client.set = AsyncMock()

        user = MagicMock()
        user.profile.telegram_id = 33

        with patch.object(UserSnapshot, "from_domain", return_value=fake_snap):
            repo = RedisUserRepo(client=client, logger=mock_logger, ttl=timedelta(minutes=5))
            await repo.set(user)

        client.set.assert_awaited_once()
        assert client.set.await_args.args[0] == "ctx:user:33"
        assert client.set.await_args.args[1] == '{"stub":true}'
        assert client.set.await_args.kwargs["expire"] == 300
