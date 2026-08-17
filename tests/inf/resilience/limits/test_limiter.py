"""Tests for the ``Limits`` wrapper around limits."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from limits import RateLimitItem, parse
from limits.errors import StorageError

from app.exceptions import LimitStorageError, TooManyRequests, UnexpectedLimitError
from infra.resilience.limits.limiter import Limits


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
            limiter="test",
            bucket="base",
            limit=str(limit_item),
            result=True,
        )
        mock_metrics.on_error.assert_not_called()

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
            limiter="test",
            bucket="base",
            limit=str(limit_item),
            result=False,
        )
        mock_backend.get_window_stats.assert_awaited_once_with(limit_item, "user:1")
        mock_metrics.on_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_hit_exceeded_uses_default_retry_when_stats_unavailable(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_metrics: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.hit = AsyncMock(return_value=False)
        mock_backend.get_window_stats = AsyncMock(
            side_effect=StorageError(RuntimeError("redis down")),
        )

        with pytest.raises(TooManyRequests) as ei:
            await rate_limits.call(limit_item, "user:1")

        assert ei.value.remaining is None
        assert ei.value.retry_after == Limits._DEFAULT_RETRY_AFTER
        assert ei.value.limit == "test:base"
        mock_metrics.on_call.assert_called_once_with(
            limiter="test",
            bucket="base",
            limit=str(limit_item),
            result=False,
        )
        mock_metrics.on_error.assert_called_once_with(
            limiter="test",
            bucket="base",
            operation="get_stats",
            error="storage",
        )

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
        mock_metrics.on_error.assert_called_once_with(
            limiter="test",
            bucket="base",
            operation="call",
            error="storage",
        )

    @pytest.mark.asyncio
    async def test_unexpected_error_maps_to_unexpected_limit_error(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_metrics: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.hit = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(UnexpectedLimitError) as ei:
            await rate_limits.call(limit_item)

        assert "test:base" in str(ei.value)
        assert isinstance(ei.value.__cause__, RuntimeError)
        mock_metrics.on_call.assert_not_called()
        mock_metrics.on_error.assert_called_once_with(
            limiter="test",
            bucket="base",
            operation="call",
            error="unexpected",
        )


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
            limiter="test",
            bucket="base",
            reset_time=50.0,
            remaining=2,
        )
        mock_metrics.on_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_storage_error(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_metrics: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.get_window_stats = AsyncMock(side_effect=StorageError(RuntimeError("down")))

        with pytest.raises(LimitStorageError):
            await rate_limits.get_window_stats(limit_item)

        mock_metrics.on_get_stats.assert_not_called()
        mock_metrics.on_error.assert_called_once_with(
            limiter="test",
            bucket="base",
            operation="get_stats",
            error="storage",
        )

    @pytest.mark.asyncio
    async def test_unexpected_error(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_metrics: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.get_window_stats = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(UnexpectedLimitError):
            await rate_limits.get_window_stats(limit_item)

        mock_metrics.on_get_stats.assert_not_called()
        mock_metrics.on_error.assert_called_once_with(
            limiter="test",
            bucket="base",
            operation="get_stats",
            error="unexpected",
        )


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
            limiter="test",
            bucket="base",
            limit=limit_item.amount,
        )
        mock_metrics.on_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_storage_error(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_metrics: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.clear = AsyncMock(side_effect=StorageError(RuntimeError("down")))

        with pytest.raises(LimitStorageError):
            await rate_limits.reset(limit_item)

        mock_metrics.on_reset.assert_not_called()
        mock_metrics.on_error.assert_called_once_with(
            limiter="test",
            bucket="base",
            operation="reset",
            error="storage",
        )

    @pytest.mark.asyncio
    async def test_unexpected_error(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_metrics: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.clear = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(UnexpectedLimitError):
            await rate_limits.reset(limit_item)

        mock_metrics.on_reset.assert_not_called()
        mock_metrics.on_error.assert_called_once_with(
            limiter="test",
            bucket="base",
            operation="reset",
            error="unexpected",
        )


def _assert_debug_fields(logger: MagicMock, message: str, limit_item: RateLimitItem) -> None:
    logger.debug.assert_any_call(
        message,
        limiter="test",
        bucket="base",
        limit=str(limit_item),
    )
    kwargs = logger.debug.call_args.kwargs
    assert "name" not in kwargs


@pytest.mark.unit
class TestLimitsDebugLogs:
    @pytest.mark.asyncio
    async def test_call_logs_limiter_and_bucket(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_logger: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.hit = AsyncMock(return_value=True)

        await rate_limits.call(limit_item, "user:1")

        _assert_debug_fields(mock_logger, "Rate limiter call request", limit_item)

    @pytest.mark.asyncio
    async def test_test_logs_limiter_and_bucket(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_logger: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.test = AsyncMock(return_value=True)

        await rate_limits.test(limit_item, "user:1")

        _assert_debug_fields(mock_logger, "Rate limiter test call request", limit_item)

    @pytest.mark.asyncio
    async def test_get_window_stats_logs_limiter_and_bucket(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_logger: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        stats = MagicMock()
        stats.reset_time = 50.0
        stats.remaining = 2
        mock_backend.get_window_stats = AsyncMock(return_value=stats)

        await rate_limits.get_window_stats(limit_item, "id")

        _assert_debug_fields(mock_logger, "Rate limit window stats request", limit_item)

    @pytest.mark.asyncio
    async def test_reset_logs_limiter_and_bucket(
        self,
        rate_limits: Limits,
        mock_backend: MagicMock,
        mock_logger: MagicMock,
        limit_item: RateLimitItem,
    ) -> None:
        mock_backend.clear = AsyncMock()

        await rate_limits.reset(limit_item, "id")

        _assert_debug_fields(mock_logger, "Rate limiter reset request", limit_item)

    def test_debug_fields_without_colon_uses_namespace_as_bucket(self) -> None:
        item = parse("1/second")
        item.namespace = "telegram"
        fields = Limits._debug_fields(item)
        assert fields["limiter"] == "telegram"
        assert fields["bucket"] == "telegram"
        assert "name" not in fields
