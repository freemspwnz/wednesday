"""Tests for NetworkContainer (DI)."""

from unittest.mock import AsyncMock, patch

import pytest

from infra.config import Config
from infra.di.network import NetworkContainer
from infra.di.observe import ObserveContainer
from infra.di.persistence import PersistenceContainer
from infra.di.resilience import ResilienceContainer
from infra.network.httpx import ProvidersRegistry


@pytest.fixture
def network_container(
    di_config: Config,
    observe_container: ObserveContainer,
    persistence_container: PersistenceContainer,
) -> NetworkContainer:
    resilience = ResilienceContainer(
        config=di_config,
        observe=observe_container,
        persistence=persistence_container,
    )
    return NetworkContainer(
        config=di_config,
        resilience=resilience,
        observe=observe_container,
    )


@pytest.mark.unit
class TestNetworkContainer:
    def test_providers_is_cached_singleton(self, network_container: NetworkContainer) -> None:
        assert network_container.providers is network_container.providers
        assert isinstance(network_container.providers, ProvidersRegistry)

    @pytest.mark.asyncio
    async def test_shutdown_without_providers_is_noop(self, network_container: NetworkContainer) -> None:
        await network_container.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_closes_initialized_providers(self, network_container: NetworkContainer) -> None:
        _ = network_container.providers
        with patch.object(network_container.providers, "aclose", new_callable=AsyncMock) as aclose:
            await network_container.shutdown()
        aclose.assert_awaited_once()
