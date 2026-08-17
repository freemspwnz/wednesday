"""Tests for PersistenceContainer (DI)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infra.config import Config
from infra.di.observe import ObserveContainer
from infra.di.persistence import PersistenceContainer
from infra.persistence.redis.registry import RedisRepoRegistry


@pytest.mark.unit
class TestPersistenceContainer:
    def test_cache_uses_wednesday_key_prefix(
        self,
        persistence_container: PersistenceContainer,
    ) -> None:
        registry = persistence_container.cache
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
        mock_uow_factory = MagicMock()
        mock_uow_factory.aclose = AsyncMock()
        with (
            patch("infra.di.persistence.build_redis", return_value=mock_redis),
            patch("infra.di.persistence.SQLAUoWFactory", return_value=mock_uow_factory),
            patch("infra.di.persistence.close_redis", new_callable=AsyncMock) as close_redis,
        ):
            pc = PersistenceContainer(config=di_config, observe=observe_container)
            _ = pc.redis
            await pc.shutdown()

        close_redis.assert_awaited_once()
        mock_uow_factory.aclose.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_shutdown_closes_initialized_uow_factory(
        self,
        di_config: Config,
        observe_container: ObserveContainer,
    ) -> None:
        mock_uow_factory = MagicMock()
        mock_uow_factory.aclose = AsyncMock()
        with (
            patch("infra.di.persistence.build_redis", return_value=MagicMock()),
            patch("infra.di.persistence.SQLAUoWFactory", return_value=mock_uow_factory),
            patch("infra.di.persistence.close_redis", new_callable=AsyncMock),
        ):
            pc = PersistenceContainer(config=di_config, observe=observe_container)
            _ = pc.uow_factory
            await pc.shutdown()

        mock_uow_factory.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_warmup_verifies_postgres_then_cache(
        self,
        di_config: Config,
        observe_container: ObserveContainer,
    ) -> None:
        order: list[str] = []
        mock_uow_factory = MagicMock()
        mock_uow_factory.warmup = AsyncMock(side_effect=lambda: order.append("postgres"))
        mock_cache = MagicMock()
        mock_cache.warmup = AsyncMock(side_effect=lambda: order.append("redis"))
        with (
            patch("infra.di.persistence.build_redis", return_value=MagicMock()),
            patch("infra.di.persistence.SQLAUoWFactory", return_value=mock_uow_factory),
        ):
            pc = PersistenceContainer(config=di_config, observe=observe_container)
            pc.__dict__["cache"] = mock_cache
            await pc.warmup()

        assert order == ["postgres", "redis"]
