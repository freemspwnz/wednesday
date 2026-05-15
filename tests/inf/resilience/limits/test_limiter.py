"""Тесты обёртки ``Limits`` над limits."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from limits import RateLimitItem, parse
from limits.errors import StorageError

from app.exceptions import LimitStorageError, TooManyRequests, UnexpectedLimitError
from infra.resilience.limits.limiter import _DEFAULT_RETRY_AFTER, Limits


@pytest.fixture
def mock_metrics() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_backend() -> MagicMock:
    return MagicMock()


@pytest.fixture
def rate_limits(
    mock_backend: MagicMock,
    mock_metrics: MagicMock,
    mock_logger: MagicMock,
) -> Limits:
    return Limits(
        limiter=mock_backend,
        metrics=mock_metrics,
        logger=mock_logger,
    )


@pytest.fixture
def limit_item() -> RateLimitItem:
    item = parse("1/second")
    item.namespace = "test:base"
    return item


@pytest.mark.unit
class TestLimitsCall:
    @pytest.mark.asyncio
    async def test_hit_allowed(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_metrics: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.hit = AsyncMock(return_value=True)

        await rate_limits.call(limit_item, "user:1")

        mock_backend.hit.assert_awaited_once_with(limit_item, "user:1", cost=1)
        mock_metrics.before_call.assert_called_once()
        mock_metrics.on_call.assert_called_once_with(
            name="test:base",
            limit=str(limit_item),
            result=True,
        )

    @pytest.mark.asyncio
    async def test_hit_exceeded_raises_too_many_requests(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_metrics: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.hit = AsyncMock(return_value=False)
        stats = MagicMock()
        stats.reset_time = time.time() + 30.5
        stats.remaining = 0
        mock_backend.get_window_stats = AsyncMock(return_value=stats)

        with pytest.raises(TooManyRequests) as ei:
            await rate_limits.call(limit_item, "user:1")

        exc = ei.value
        assert exc.limit == "test:base"
        assert exc.remaining == 0
        assert exc.reset_at == stats.reset_time
        assert exc.retry_after == 31
        mock_metrics.on_call.assert_called_once_with(
            name="test:base",
            limit=str(limit_item),
            result=False,
        )
        mock_backend.get_window_stats.assert_awaited_once_with(limit_item, "user:1")

    @pytest.mark.asyncio
    async def test_hit_exceeded_uses_default_retry_when_stats_unavailable(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.hit = AsyncMock(return_value=False)
        mock_backend.get_window_stats = AsyncMock(
            side_effect=StorageError(RuntimeError("redis down")),
        )

        with pytest.raises(TooManyRequests) as ei:
            await rate_limits.call(limit_item, "user:1")

        assert ei.value.remaining is None
        assert ei.value.retry_after == _DEFAULT_RETRY_AFTER
        assert ei.value.limit == "test:base"

    @pytest.mark.asyncio
    async def test_storage_error_maps_to_limit_storage_error(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_metrics: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.hit = AsyncMock(side_effect=StorageError(RuntimeError("redis down")))

        with pytest.raises(LimitStorageError) as ei:
            await rate_limits.call(limit_item, "user:1")

        assert "backend unavailable" in str(ei.value)
        assert isinstance(ei.value.__cause__, StorageError)
        mock_metrics.before_call.assert_called_once()
        mock_metrics.on_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_unexpected_error_maps_to_unexpected_limit_error(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.hit = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(UnexpectedLimitError) as ei:
            await rate_limits.call(limit_item)

        assert "test:base" in str(ei.value)
        assert isinstance(ei.value.__cause__, RuntimeError)


@pytest.mark.unit
class TestLimitsDecorator:
    @pytest.mark.asyncio
    async def test_decorator_runs_call_before_wrapped(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.hit = AsyncMock(return_value=True)
        order: list[str] = []

        @rate_limits(limit_item, "k")
        async def work() -> str:
            order.append("work")
            return "ok"

        assert await work() == "ok"
        assert order == ["work"]
        mock_backend.hit.assert_awaited_once()


@pytest.mark.unit
class TestLimitsGetWindowStats:
    @pytest.mark.asyncio
    async def test_success(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_metrics: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        stats = MagicMock()
        stats.reset_time = 50.0
        stats.remaining = 2
        mock_backend.get_window_stats = AsyncMock(return_value=stats)

        out = await rate_limits.get_window_stats(limit_item, "id")

        assert out is stats
        mock_metrics.on_get_stats.assert_called_once_with(
            name="test:base",
            reset_time=50.0,
            remaining=2,
        )

    @pytest.mark.asyncio
    async def test_storage_error(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.get_window_stats = AsyncMock(side_effect=StorageError(RuntimeError("down")))

        with pytest.raises(LimitStorageError):
            await rate_limits.get_window_stats(limit_item)


@pytest.mark.unit
class TestLimitsReset:
    @pytest.mark.asyncio
    async def test_success(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_metrics: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.clear = AsyncMock()

        await rate_limits.reset(limit_item, "id")

        mock_backend.clear.assert_awaited_once_with(limit_item, "id")
        mock_metrics.on_reset.assert_called_once_with(
            name="test:base",
            limit=limit_item.amount,
        )

    @pytest.mark.asyncio
    async def test_storage_error(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.clear = AsyncMock(side_effect=StorageError(RuntimeError("down")))

        with pytest.raises(LimitStorageError):
            await rate_limits.reset(limit_item)
