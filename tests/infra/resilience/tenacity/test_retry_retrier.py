"""Тесты TenacityRetrier."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.exceptions import MaxAttemptsExhaustedError
from infra.config import RetryConfig
from infra.resilience.tenacity.retrier import TenacityRetrier


def _fast_config(*, attempts: int = 2, reraise: bool = False) -> RetryConfig:
    return RetryConfig(
        name="unit",
        attempts=attempts,
        reraise=reraise,
        initial=0.0,
        max=0.0,
        exp_base=2.0,
        jitter=0.0,
    )


@pytest.mark.unit
class TestTenacityRetrier:
    @pytest.mark.asyncio
    async def test_execute_success_first_attempt(
        self,
        mock_logger: MagicMock,
    ) -> None:
        metrics = MagicMock()
        r = TenacityRetrier(
            config=_fast_config(attempts=1, reraise=False),
            predicate=lambda e: isinstance(e, ValueError),
            metrics=metrics,
            logger=mock_logger,
        )

        async def ok() -> str:
            return "ok"

        assert await r.execute(ok) == "ok"
        metrics.on_retry.assert_called()
        assert metrics.on_retry.call_args.kwargs["status"] == "success"
        metrics.after_retry.assert_called()

    @pytest.mark.asyncio
    async def test_execute_retries_then_succeeds(
        self,
        mock_logger: MagicMock,
    ) -> None:
        metrics = MagicMock()
        r = TenacityRetrier(
            config=_fast_config(attempts=3, reraise=False),
            predicate=lambda e: isinstance(e, ValueError),
            metrics=metrics,
            logger=mock_logger,
        )
        calls = {"n": 0}

        async def flaky() -> int:
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("retry me")
            return 42

        assert await r.execute(flaky) == 42
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_execute_non_retryable_propagates_immediately(
        self,
        mock_logger: MagicMock,
    ) -> None:
        metrics = MagicMock()
        r = TenacityRetrier(
            config=_fast_config(attempts=3, reraise=False),
            predicate=lambda e: isinstance(e, ValueError),
            metrics=metrics,
            logger=mock_logger,
        )

        async def bad() -> None:
            raise KeyError("missing")

        with pytest.raises(KeyError, match="missing"):
            await r.execute(bad)

    @pytest.mark.asyncio
    async def test_execute_reraise_false_exhausts_raises_max_attempts(
        self,
        mock_logger: MagicMock,
    ) -> None:
        metrics = MagicMock()
        r = TenacityRetrier(
            config=_fast_config(attempts=2, reraise=False),
            predicate=lambda e: isinstance(e, ValueError),
            metrics=metrics,
            logger=mock_logger,
        )

        async def always_fail() -> None:
            raise ValueError("boom")

        with pytest.raises(MaxAttemptsExhaustedError) as exc_info:
            await r.execute(always_fail)

        err = exc_info.value
        assert err.attempts == 2
        assert "unit" in str(err)
        assert isinstance(err.__cause__, Exception)

    @pytest.mark.asyncio
    async def test_execute_reraise_true_propagates_last_exception(
        self,
        mock_logger: MagicMock,
    ) -> None:
        metrics = MagicMock()
        r = TenacityRetrier(
            config=_fast_config(attempts=2, reraise=True),
            predicate=lambda e: isinstance(e, ValueError),
            metrics=metrics,
            logger=mock_logger,
        )

        async def always_fail() -> None:
            raise ValueError("last")

        with pytest.raises(ValueError, match="last"):
            await r.execute(always_fail)
