"""Фикстуры для тестов infra.di."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infra.config import Config
from infra.config.observe import MetricsConfig
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

    with (
        patch("infra.di.persistence.build_redis", return_value=mock_redis),
        patch("infra.di.persistence.RedisClient", return_value=MagicMock()),
        patch("infra.di.persistence.close_engine", new_callable=AsyncMock),
        patch("infra.di.persistence.close_redis", new_callable=AsyncMock),
    ):
        yield PersistenceContainer(config=di_config, observe=observe_container)


@pytest.fixture
def container(di_config: Config) -> Iterator[Container]:
    mock_redis = MagicMock()
    mock_redis.connection_pool = MagicMock()

    with (
        patch("infra.di.persistence.build_redis", return_value=mock_redis),
        patch("infra.di.persistence.RedisClient", return_value=MagicMock()),
        patch("infra.di.persistence.close_engine", new_callable=AsyncMock),
        patch("infra.di.persistence.close_redis", new_callable=AsyncMock),
    ):
        yield Container(config=di_config)
