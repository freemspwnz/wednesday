"""Tests for ResiliencePolicy composition."""

from unittest.mock import MagicMock

import pytest

from infra.network.httpx.policy import ResiliencePolicy

from .conftest import PassThroughBreaker, PassThroughLimiter, PassThroughRetrier


@pytest.mark.unit
class TestResiliencePolicy:
    @pytest.mark.asyncio
    async def test_apply_runs_func_through_passthrough_layers(self) -> None:
        policy = ResiliencePolicy(
            retrier=PassThroughRetrier(),
            breaker=PassThroughBreaker(),
            limiter=PassThroughLimiter(),
        )

        async def ping() -> str:
            return "pong"

        assert await policy.apply(ping) == "pong"

    @pytest.mark.asyncio
    async def test_call_wrapper_delegates_to_apply(self) -> None:
        policy = ResiliencePolicy(
            retrier=PassThroughRetrier(),
            breaker=PassThroughBreaker(),
            limiter=PassThroughLimiter(),
        )

        async def add(a: int, b: int) -> int:
            return a + b

        wrapped = policy(add)
        assert await wrapped(2, 3) == 5

    def test_missing_base_limit_raises(self) -> None:
        limiter = MagicMock()
        limiter.limits = {"other": "x"}
        with pytest.raises(KeyError):
            ResiliencePolicy(
                retrier=PassThroughRetrier(),
                breaker=PassThroughBreaker(),
                limiter=limiter,
            )
