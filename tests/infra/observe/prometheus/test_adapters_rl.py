"""Тесты LimitsMetrics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infra.observe.prometheus.adapters.rl import LimitsMetrics


@pytest.mark.unit
class TestLimitsMetrics:
    def test_on_call(self) -> None:
        coll = MagicMock()
        m = LimitsMetrics(collector=coll)
        m.before_call()
        m.on_call(name="ns", limit="10/hour", result=True)
        assert coll.observe.called
        assert coll.increment.called

    def test_on_get_stats_success(self) -> None:
        coll = MagicMock()
        m = LimitsMetrics(collector=coll)
        m.before_call()
        m.on_get_stats(name="ns", reset_time=123.0, remaining=3)
        assert coll.set_gauge.call_count == 2
        succ = coll.increment.call_args.kwargs["labels"]["result"]
        assert succ == "success"

    def test_on_reset(self) -> None:
        coll = MagicMock()
        m = LimitsMetrics(collector=coll)
        m.before_call()
        m.on_reset(name="ns", limit=100)
        assert coll.increment.call_args.kwargs["name"] == "rl_reset_calls_total"
