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

    def test_map_state_unknown(self) -> None:
        assert AsyncbreakerMetrics._map_state("WEIRD") == -1.0
