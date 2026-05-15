"""Тесты AsyncbreakerMetrics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infra.observe.prometheus.adapters.cb import AsyncbreakerMetrics


@pytest.mark.unit
class TestAsyncbreakerMetrics:
    def test_after_call_records_metrics(self) -> None:
        coll = MagicMock()
        m = AsyncbreakerMetrics(collector=coll)
        m.before_call()
        m.after_call(name="cb1", result="success")
        assert coll.observe.call_count == 1
        assert coll.increment.call_count == 1
        args_kw = coll.increment.call_args
        assert args_kw.kwargs["name"] == "cb_calls_total"

    def test_on_state_change(self) -> None:
        coll = MagicMock()
        m = AsyncbreakerMetrics(collector=coll)
        m.on_state_change(name="cb1", old_state="CLOSED", new_state="OPEN")
        assert coll.set_gauge.called
        assert coll.increment.called
        assert coll.observe.called

    def test_on_state_change_unknown_new_state_maps_gauge_to_negative_one(self) -> None:
        coll = MagicMock()
        m = AsyncbreakerMetrics(collector=coll)
        m.on_state_change(name="cb1", old_state="closed", new_state="weird_unknown")
        gauge_kw = coll.set_gauge.call_args.kwargs
        assert gauge_kw["name"] == "cb_state"
        assert gauge_kw["value"] == -1.0
