"""Tests for ResilienceContainer (DI)."""

from unittest.mock import MagicMock, patch

import pytest

from infra.config import Config
from infra.config.resilience.asyncbreaker import CircuitBreakerConfig
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
    def test_limiter_passes_config_env_and_version(
        self,
        resilience_container: ResilienceContainer,
    ) -> None:
        config = RateLimitConfig(name="telegram", storage="memory")
        with patch("infra.di.resilience.rl_factory") as factory:
            factory.return_value = MagicMock(spec=Limits)
            resilience_container.limiter(config=config)

        factory.assert_called_once()
        call_kwargs = factory.call_args.kwargs
        assert call_kwargs["config"] is config
        assert call_kwargs["env"] == "STAGE"
        assert call_kwargs["version"] == "1.2.3"

    def test_retrier_uses_provided_config(
        self,
        resilience_container: ResilienceContainer,
    ) -> None:
        config = RetryConfig(name="telegram", attempts=3)
        with patch("infra.di.resilience.Tenacity") as tenacity_cls:
            tenacity_cls.return_value = MagicMock(spec=Tenacity)
            resilience_container.retrier(config=config)

        tenacity_cls.assert_called_once()
        assert tenacity_cls.call_args.kwargs["config"] is config

    def test_breaker_passes_env_version_to_factory(
        self,
        resilience_container: ResilienceContainer,
    ) -> None:
        config = CircuitBreakerConfig(name="api", storage="memory")
        with patch("infra.di.resilience.cb_factory") as factory:
            factory.return_value = MagicMock()
            resilience_container.breaker(config=config)

        factory.assert_called_once()
        assert factory.call_args.kwargs["config"] is config
        assert factory.call_args.kwargs["env"] == "STAGE"
        assert factory.call_args.kwargs["version"] == "1.2.3"

    def test_limiter_requires_explicit_config(
        self,
        resilience_container: ResilienceContainer,
    ) -> None:
        with pytest.raises(TypeError):
            resilience_container.limiter()  # type: ignore[call-arg]

    def test_retrier_requires_explicit_config(
        self,
        resilience_container: ResilienceContainer,
    ) -> None:
        with pytest.raises(TypeError):
            resilience_container.retrier()  # type: ignore[call-arg]
