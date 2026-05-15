"""Тесты ResilienceContainer (DI)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from infra.config import Config
from infra.config.resilience.limits import RateLimitConfig
from infra.config.resilience.tenacity import RetryConfig
from infra.di.observe import ObserveContainer
from infra.di.persistence import PersistenceContainer
from infra.di.resilience import ResilienceContainer
from infra.resilience.limits.limiter import Limits
from infra.resilience.tenacity import Tenacity


@pytest.fixture
def resilience_container(
    di_config: Config,
    observe_container: ObserveContainer,
    persistence_container: PersistenceContainer,
) -> ResilienceContainer:
    return ResilienceContainer(
        config=di_config,
        observe=observe_container,
        persistence=persistence_container,
    )


@pytest.mark.unit
class TestResilienceContainer:
    def test_rate_limiter_uses_root_config_by_default(
        self,
        resilience_container: ResilienceContainer,
        di_config: Config,
    ) -> None:
        with patch("infra.di.resilience.rl_factory") as factory:
            factory.return_value = MagicMock(spec=Limits)
            resilience_container.rate_limiter()

        factory.assert_called_once()
        call_kwargs = factory.call_args.kwargs
        assert call_kwargs["config"] is di_config.rate_limit
        assert call_kwargs["env"] == "STAGE"
        assert call_kwargs["version"] == "1.2.3"

    def test_retry_uses_root_config_by_default(
        self,
        resilience_container: ResilienceContainer,
        di_config: Config,
    ) -> None:
        with patch("infra.di.resilience.Tenacity") as tenacity_cls:
            tenacity_cls.return_value = MagicMock(spec=Tenacity)
            resilience_container.retry()

        tenacity_cls.assert_called_once()
        assert tenacity_cls.call_args.kwargs["config"] is di_config.retry

    def test_circuit_breaker_passes_env_version_to_factory(
        self,
        resilience_container: ResilienceContainer,
    ) -> None:
        with patch("infra.di.resilience.cb_factory") as factory:
            factory.return_value = MagicMock()
            resilience_container.circuit_breaker()

        factory.assert_called_once()
        assert factory.call_args.kwargs["env"] == "STAGE"
        assert factory.call_args.kwargs["version"] == "1.2.3"

    def test_rate_limiter_accepts_override_config(
        self,
        resilience_container: ResilienceContainer,
    ) -> None:
        override = RateLimitConfig(name="custom", storage="memory")
        with patch("infra.di.resilience.rl_factory") as factory:
            factory.return_value = MagicMock(spec=Limits)
            resilience_container.rate_limiter(config=override)

        assert factory.call_args.kwargs["config"] is override

    def test_retry_accepts_override_config(
        self,
        resilience_container: ResilienceContainer,
    ) -> None:
        override = RetryConfig(name="api", attempts=5)
        with patch("infra.di.resilience.Tenacity") as tenacity_cls:
            tenacity_cls.return_value = MagicMock(spec=Tenacity)
            resilience_container.retry(config=override)

        assert tenacity_cls.call_args.kwargs["config"] is override
