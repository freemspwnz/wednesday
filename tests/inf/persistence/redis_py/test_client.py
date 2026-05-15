"""Тесты RedisClient: маппинг ошибок redis-py → app.exceptions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.exceptions as redis_exc

from app.exceptions import CacheTimeoutError, CacheUnavailableError, UnexpectedCacheError
from infra.persistence.redis.client import RedisClient


@pytest.mark.unit
class TestRedisClientErrors:
    @pytest.mark.asyncio
    async def test_get_maps_connection_error(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=redis_exc.ConnectionError("refused"))
        client = RedisClient(redis=redis, metrics=cache_metrics, logger=mock_logger)

        with pytest.raises(CacheUnavailableError) as exc_info:
            await client.get("ctx:user:1")

        assert exc_info.value.operation == "get"
        assert isinstance(exc_info.value.__cause__, redis_exc.ConnectionError)

    @pytest.mark.asyncio
    async def test_get_maps_timeout_error(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=redis_exc.TimeoutError("timed out"))
        client = RedisClient(redis=redis, metrics=cache_metrics, logger=mock_logger)

        with pytest.raises(CacheTimeoutError) as exc_info:
            await client.get("k")

        assert exc_info.value.operation == "get"

    @pytest.mark.asyncio
    async def test_get_maps_busy_loading_to_unavailable(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=redis_exc.BusyLoadingError("LOADING"))
        client = RedisClient(redis=redis, metrics=cache_metrics, logger=mock_logger)

        with pytest.raises(CacheUnavailableError):
            await client.get("k")

    @pytest.mark.asyncio
    async def test_set_maps_response_error_to_unexpected(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        redis.set = AsyncMock(side_effect=redis_exc.ResponseError("OOM"))
        client = RedisClient(redis=redis, metrics=cache_metrics, logger=mock_logger)

        with pytest.raises(UnexpectedCacheError) as exc_info:
            await client.set("k", "v")

        assert isinstance(exc_info.value.__cause__, redis_exc.ResponseError)

    @pytest.mark.asyncio
    async def test_get_success_sets_hit_metric(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        redis.get = AsyncMock(return_value=b"payload")
        client = RedisClient(redis=redis, metrics=cache_metrics, logger=mock_logger)

        result = await client.get("k")
        assert result == b"payload"


@pytest.mark.unit
class TestRedisClientOperations:
    @pytest.mark.asyncio
    async def test_delete_tracks_metrics(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        redis.delete = AsyncMock(return_value=1)
        client = RedisClient(redis=redis, metrics=cache_metrics, logger=mock_logger)

        await client.delete("k1")

        redis.delete.assert_awaited_once_with("k1")

    @pytest.mark.asyncio
    async def test_exists_true_and_false(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        redis.exists = AsyncMock(side_effect=[1, 0])
        client = RedisClient(redis=redis, metrics=cache_metrics, logger=mock_logger)

        assert await client.exists("a") is True
        assert await client.exists("b") is False

    @pytest.mark.asyncio
    async def test_set_passes_timedelta_expire(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        from datetime import timedelta

        redis = MagicMock()
        redis.set = AsyncMock(return_value=True)
        client = RedisClient(redis=redis, metrics=cache_metrics, logger=mock_logger)

        await client.set("k", "v", expire=timedelta(seconds=30))

        redis.set.assert_awaited_once_with("k", "v", ex=timedelta(seconds=30))

    @pytest.mark.asyncio
    async def test_get_queue_size_sets_gauge(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        redis.llen = AsyncMock(return_value=4)
        client = RedisClient(redis=redis, metrics=cache_metrics, logger=mock_logger)

        assert await client.get_queue_size("q:tasks") == 4
        redis.llen.assert_awaited_once_with("q:tasks")
        cache_metrics.set_queue_size.assert_called_once_with("q:tasks", 4)

    @pytest.mark.asyncio
    async def test_get_maps_try_again_to_unavailable(
        self,
        cache_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        redis = MagicMock()
        redis.get = AsyncMock(side_effect=redis_exc.TryAgainError("retry"))
        client = RedisClient(redis=redis, metrics=cache_metrics, logger=mock_logger)

        with pytest.raises(CacheUnavailableError):
            await client.get("k")
