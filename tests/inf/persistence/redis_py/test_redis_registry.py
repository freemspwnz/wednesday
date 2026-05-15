"""Тесты RedisRepoRegistry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from infra.persistence.redis.registry import RedisRepoRegistry


@pytest.mark.unit
class TestRedisRepoRegistry:
    def test_user_and_chat_are_cached_singletons(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        reg = RedisRepoRegistry(client=client, logger=mock_logger)
        assert reg.user is reg.user
        assert reg.chat is reg.chat

    @pytest.mark.asyncio
    async def test_forwards_key_prefix_to_user_repo(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value=None)
        reg = RedisRepoRegistry(client=client, logger=mock_logger, key_prefix="STAGE:1.2.3:ctx")
        assert await reg.user.get_by_id(10) is None
        client.get.assert_awaited_once_with("STAGE:1.2.3:ctx:user:10")

    @pytest.mark.asyncio
    async def test_forwards_key_prefix_to_chat_repo(self, mock_logger: MagicMock) -> None:
        client = MagicMock()
        client.get = AsyncMock(return_value=None)
        reg = RedisRepoRegistry(client=client, logger=mock_logger, key_prefix="STAGE:1.2.3:ctx")
        assert await reg.chat.get_by_id(11) is None
        client.get.assert_awaited_once_with("STAGE:1.2.3:ctx:chat:11")
