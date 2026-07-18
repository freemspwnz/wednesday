"""Tests for ProvidersRegistry."""

from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from infra.config import Config, GigaChatConfig, HttpConfig, HttpTimeoutConfig
from infra.config.observe import MetricsConfig
from infra.config.resilience.asyncbreaker import CircuitBreakerConfig
from infra.config.resilience.limits import RateLimitConfig
from infra.config.resilience.tenacity import RetryConfig
from infra.network.httpx.factory import HttpClientFactory
from infra.network.httpx.providers import SberClient
from infra.network.httpx.registry import ProvidersRegistry

from .conftest import PassThroughBreaker, PassThroughLimiter, PassThroughRetrier


def _registry(*, mock_logger: MagicMock, mock_http_metrics: MagicMock) -> ProvidersRegistry:
    http = HttpConfig(
        base_url="https://gigachat.example.com/v1/",
        verify=False,
        http2=False,
        timeouts={
            "base": HttpTimeoutConfig(timeout=5),
            "image": HttpTimeoutConfig(timeout=5),
            "prompt": HttpTimeoutConfig(timeout=5),
            "models": HttpTimeoutConfig(timeout=5),
        },
    )
    config = Config(
        _env_file=None,
        metrics=MetricsConfig(enabled=False),
        gigachat=GigaChatConfig(
            auth_key=SecretStr("test-key"),
            http=http,
            retrier=RetryConfig(name="gigachat", attempts=1, reraise=True, initial=0.0, max=0.0, jitter=0.0),
            limiter=RateLimitConfig(name="gigachat", storage="memory", limits={"base": "100/second"}),
            breaker=CircuitBreakerConfig(name="gigachat", storage="memory"),
        ),
    )
    factory = HttpClientFactory(
        retrier=lambda **_: PassThroughRetrier(),
        breaker=lambda **_: PassThroughBreaker(),
        limiter=lambda **_: PassThroughLimiter(),
        metrics=mock_http_metrics,
        logger=mock_logger,
    )
    return ProvidersRegistry(config=config, factory=factory, logger=mock_logger)


@pytest.mark.unit
class TestProvidersRegistry:
    @pytest.mark.asyncio
    async def test_sber_is_cached_and_closed(
        self,
        mock_logger: MagicMock,
        mock_http_metrics: MagicMock,
    ) -> None:
        registry = _registry(mock_logger=mock_logger, mock_http_metrics=mock_http_metrics)
        sber = registry.sber
        assert isinstance(sber, SberClient)
        assert registry.sber is sber
        await registry.aclose()
        assert "sber" not in registry.__dict__

    @pytest.mark.asyncio
    async def test_aclose_without_sber_is_noop(
        self,
        mock_logger: MagicMock,
        mock_http_metrics: MagicMock,
    ) -> None:
        registry = _registry(mock_logger=mock_logger, mock_http_metrics=mock_http_metrics)
        await registry.aclose()
