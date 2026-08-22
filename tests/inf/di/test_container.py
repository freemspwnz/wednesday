"""Tests for the root Container (DI)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infra.config import Config
from infra.di.container import Container
from infra.di.network import NetworkContainer
from infra.di.observe import ObserveContainer
from infra.di.persistence import PersistenceContainer
from infra.di.resilience import ResilienceContainer
from infra.di.scope import ScopeContainer


@pytest.mark.unit
class TestContainer:
    def test_observe_is_cached_singleton(self, container: Container) -> None:
        assert container.observe is container.observe
        assert isinstance(container.observe, ObserveContainer)

    def test_persistence_is_cached_singleton(self, container: Container) -> None:
        assert container.persistence is container.persistence
        assert isinstance(container.persistence, PersistenceContainer)

    def test_resilience_is_cached_singleton(self, container: Container) -> None:
        assert container.resilience is container.resilience
        assert isinstance(container.resilience, ResilienceContainer)

    def test_network_is_cached_singleton(self, container: Container) -> None:
        assert container.network is container.network
        assert isinstance(container.network, NetworkContainer)

    @pytest.mark.asyncio
    async def test_get_scope_yields_scope_container(self, container: Container) -> None:
        with patch("infra.di.scope.UserManagementUseCase") as user_management_uc_cls:
            user_management_uc_cls.return_value = MagicMock()
            async with container.scope() as scope:
                assert isinstance(scope, ScopeContainer)
                assert scope.logger is container.observe.logger
                assert scope.user_management_uc is user_management_uc_cls.return_value

    @pytest.mark.asyncio
    async def test_shutdown_without_touching_persistence(self, di_config: Config) -> None:
        with patch("infra.di.persistence.build_redis"):
            bare = Container(config=di_config)
            await bare.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_invokes_persistence_shutdown(self, container: Container) -> None:
        _ = container.persistence.redis
        with patch.object(
            container.persistence,
            "shutdown",
            new_callable=AsyncMock,
        ) as shutdown_mock:
            await container.shutdown()

        shutdown_mock.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_shutdown_invokes_network_shutdown(self, container: Container) -> None:
        _ = container.network
        with patch.object(
            container.network,
            "shutdown",
            new_callable=AsyncMock,
        ) as shutdown_mock:
            await container.shutdown()

        shutdown_mock.assert_awaited_once()
