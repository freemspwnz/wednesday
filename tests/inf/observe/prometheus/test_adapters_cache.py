"""Тесты RedisMetrics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infra.observe.prometheus.adapters.cache import RedisMetrics


@pytest.mark.unit
class TestRedisMetrics:
    @pytest.mark.asyncio
    async def test_track_success_no_hit(self) -> None:
        coll = MagicMock()
        m = RedisMetrics(collector=coll)
        async with m.track("set"):
            pass
        labels = coll.increment.call_args.kwargs["labels"]
        assert labels["status"] == "success"

    @pytest.mark.asyncio
    async def test_track_hit(self) -> None:
        coll = MagicMock()
        m = RedisMetrics(collector=coll)
        async with m.track("get") as op:
            op.hit = True
        assert coll.increment.call_args.kwargs["labels"]["status"] == "hit"

    @pytest.mark.asyncio
    async def test_track_miss(self) -> None:
        coll = MagicMock()
        m = RedisMetrics(collector=coll)
        async with m.track("get") as op:
            op.hit = False
        assert coll.increment.call_args.kwargs["labels"]["status"] == "miss"

    @pytest.mark.asyncio
    async def test_track_error(self) -> None:
        coll = MagicMock()
        m = RedisMetrics(collector=coll)
        with pytest.raises(RuntimeError, match="boom"):
            async with m.track("get"):
                raise RuntimeError("boom")
        assert coll.increment.call_args.kwargs["labels"]["status"] == "error"

    def test_set_queue_size(self) -> None:
        coll = MagicMock()
        m = RedisMetrics(collector=coll)
        m.set_queue_size("q1", 7)
        coll.set_gauge.assert_called_once()
