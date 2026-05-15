"""Тесты PersistenceContainer (DI)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infra.config import Config
from infra.di.observe import ObserveContainer
from infra.di.persistence import PersistenceContainer
from infra.persistence.redis.registry import RedisRepoRegistry


@pytest.mark.unit
class TestPersistenceContainer:
    def test_cache_repo_registry_uses_wednesday_key_prefix(
        self,
        persistence_container: PersistenceContainer,
    ) -> None:
        registry = persistence_container.cache_repo_registry
        assert isinstance(registry, RedisRepoRegistry)
        assert registry._key_prefix == "wednesday:STAGE:1.2.3:ctx"

    def test_redis_singleton_cached(
        self,
        persistence_container: PersistenceContainer,
    ) -> None:
        assert persistence_container.redis is persistence_container.redis

    @pytest.mark.asyncio
    async def test_shutdown_closes_initialized_redis(
        self,
        di_config: Config,
        observe_container: ObserveContainer,
    ) -> None:
        mock_redis = MagicMock()
        with (
            patch("infra.di.persistence.build_redis", return_value=mock_redis),
            patch("infra.di.persistence.RedisClient", return_value=MagicMock()),
            patch("infra.di.persistence.close_redis", new_callable=AsyncMock) as close_redis,
            patch("infra.di.persistence.close_engine", new_callable=AsyncMock) as close_engine,
        ):
            pc = PersistenceContainer(config=di_config, observe=observe_container)
            _ = pc.redis
            await pc.shutdown()

        close_redis.assert_awaited_once()
        close_engine.assert_not_awaited()
