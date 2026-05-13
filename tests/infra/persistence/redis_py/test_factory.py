"""Тесты фабрики Redis (build / close)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr
from redis.exceptions import ConnectionError as RedisConnectionError

from infra.config.persistence.redis import RedisConfig
from infra.persistence.redis import factory as redis_factory_mod
from infra.persistence.redis.factory import build_redis, close_redis


@pytest.mark.unit
class TestBuildRedis:
    def test_build_redis_from_url_kwargs(self, mock_logger: MagicMock) -> None:
        cfg = RedisConfig(password=SecretStr("secret"))
        fake = MagicMock()
        with patch("infra.persistence.redis.factory.Redis.from_url", return_value=fake) as from_url:
            client = build_redis(config=cfg, logger=mock_logger)

        assert client is fake
        from_url.assert_called_once()
        _, kwargs = from_url.call_args
        assert kwargs["url"] == cfg.dsn
        assert kwargs["decode_responses"] is True
        assert kwargs["max_connections"] == 10
        assert kwargs["socket_timeout"] == 10.0


@pytest.mark.unit
class TestCloseRedis:
    @pytest.mark.asyncio
    async def test_close_redis_awaits_aclose(self, mock_logger: MagicMock) -> None:
        redis = AsyncMock()
        await close_redis(redis=redis, logger=mock_logger)
        redis.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_close_redis_logs_on_connection_error(self, mock_logger: MagicMock) -> None:
        redis = AsyncMock()
        redis.aclose = AsyncMock(side_effect=RedisConnectionError("gone"))
        await close_redis(redis=redis, logger=mock_logger)
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_close_redis_logs_noncritical_exception(self, mock_logger: MagicMock) -> None:
        redis = AsyncMock()
        redis.aclose = AsyncMock(side_effect=RuntimeError("unexpected"))
        await close_redis(redis=redis, logger=mock_logger)
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_close_redis_timeout_on_slow_aclose(self, mock_logger: MagicMock) -> None:
        redis = MagicMock()

        async def slow_aclose() -> None:
            await asyncio.sleep(10)

        redis.aclose = AsyncMock(side_effect=slow_aclose)

        with patch.object(redis_factory_mod, "_REDIS_CLOSE_TIMEOUT", 0.05):
            await close_redis(redis=redis, logger=mock_logger)

        mock_logger.warning.assert_called()
