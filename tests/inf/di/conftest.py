"""Fixtures for infra.di tests."""

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from infra.config import Config
from infra.config.observe import MetricsConfig
from infra.config.presentation import TelegramConfig
from infra.di.container import Container
from infra.di.observe import ObserveContainer
from infra.di.persistence import PersistenceContainer


@pytest.fixture
def di_config(monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("VERSION", raising=False)
    return Config(
        _env_file=None,
        ENV="STAGE",
        VERSION="1.2.3",
        metrics=MetricsConfig(enabled=False),
        telegram=TelegramConfig(token=SecretStr("test-token"), admin_id=1),
    )


@pytest.fixture
def observe_container(di_config: Config) -> ObserveContainer:
    return ObserveContainer(config=di_config)


@pytest.fixture
def persistence_container(
    di_config: Config,
    observe_container: ObserveContainer,
) -> Iterator[PersistenceContainer]:
    mock_redis = MagicMock()
    mock_redis.connection_pool = MagicMock()
    mock_uow_factory = MagicMock()
    mock_uow_factory.aclose = AsyncMock()

    with (
        patch("infra.di.persistence.build_redis", return_value=mock_redis),
        patch("infra.di.persistence.SQLAUoWFactory", return_value=mock_uow_factory),
        patch("infra.di.persistence.close_redis", new_callable=AsyncMock),
    ):
        yield PersistenceContainer(config=di_config, observe=observe_container)


@pytest.fixture
def container(di_config: Config) -> Iterator[Container]:
    mock_redis = MagicMock()
    mock_redis.connection_pool = MagicMock()
    mock_uow_factory = MagicMock()
    mock_uow_factory.aclose = AsyncMock()

    with (
        patch("infra.di.persistence.build_redis", return_value=mock_redis),
        patch("infra.di.persistence.SQLAUoWFactory", return_value=mock_uow_factory),
        patch("infra.di.persistence.close_redis", new_callable=AsyncMock),
    ):
        yield Container(config=di_config)
