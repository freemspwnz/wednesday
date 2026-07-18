"""RedisRepoRegistry tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from infra.persistence.redis.client import RedisClient
from infra.persistence.redis.registry import RedisRepoRegistry
from infra.persistence.redis.repos.chat import RedisChatRepo
from infra.persistence.redis.repos.user import RedisUserRepo


@pytest.mark.unit
class TestRedisRepoRegistry:
    def test_users_and_chats_are_cached_singletons(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        reg = RedisRepoRegistry(
            redis=redis,
            metrics=cache_metrics,
            logger=mock_logger,
        )
        assert isinstance(reg.users, RedisUserRepo)
        assert isinstance(reg.chats, RedisChatRepo)
        assert reg.users is reg.users
        assert reg.chats is reg.chats
        assert isinstance(reg._client, RedisClient)
        assert reg.users._client is reg._client
        assert reg.chats._client is reg._client

    @pytest.mark.asyncio
    async def test_forwards_key_prefix_to_user_repo(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        reg = RedisRepoRegistry(
            redis=redis,
            metrics=cache_metrics,
            logger=mock_logger,
            key_prefix="STAGE:1.2.3:ctx",
        )
        assert await reg.users.get_by_id(10) is None
        redis.get.assert_awaited_once_with("STAGE:1.2.3:ctx:user:10")

    @pytest.mark.asyncio
    async def test_forwards_key_prefix_to_chat_repo(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        reg = RedisRepoRegistry(
            redis=redis,
            metrics=cache_metrics,
            logger=mock_logger,
            key_prefix="STAGE:1.2.3:ctx",
        )
        assert await reg.chats.get_by_id(11) is None
        redis.get.assert_awaited_once_with("STAGE:1.2.3:ctx:chat:11")
