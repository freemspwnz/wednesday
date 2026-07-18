"""Tests for HttpClientFactory."""

from unittest.mock import MagicMock

import pytest

from infra.config import CircuitBreakerConfig, HttpConfig, RateLimitConfig, RetryConfig
from infra.network.httpx.client import HttpClient
from infra.network.httpx.factory import HttpClientFactory

from .conftest import PassThroughBreaker, PassThroughLimiter, PassThroughRetrier


@pytest.mark.unit
class TestHttpClientFactory:
    @pytest.mark.asyncio
    async def test_builds_and_closes_client(
        self,
        http_config: HttpConfig,
        mock_http_metrics: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        factory = HttpClientFactory(
            retrier=lambda **_: PassThroughRetrier(),
            breaker=lambda **_: PassThroughBreaker(),
            limiter=lambda **_: PassThroughLimiter(),
            metrics=mock_http_metrics,
            logger=mock_logger,
        )
        client = factory(
            http=http_config,
            retrier=RetryConfig(name="unit", attempts=1, reraise=True, initial=0.0, max=0.0, jitter=0.0),
            breaker=CircuitBreakerConfig(name="unit", storage="memory"),
            limiter=RateLimitConfig(name="unit", storage="memory", limits={"base": "10/second"}),
        )
        assert isinstance(client, HttpClient)
        assert str(client.raw.base_url).startswith("https://api.example.com/v1")
        await factory.aclose(client)
