"""Тесты TenacityMetrics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infra.observe.prometheus.adapters.retry import TenacityMetrics


@pytest.mark.unit
class TestTenacityMetrics:
    def test_before_after_retry(self) -> None:
        coll = MagicMock()
        m = TenacityMetrics(collector=coll)
        m.before_retry()
        m.after_retry(name="r1")
        coll.observe.assert_called()

    def test_on_retry(self) -> None:
        coll = MagicMock()
        m = TenacityMetrics(collector=coll)
        m.on_retry(name="r1", attempt=2, status="retry")
        assert coll.increment.called
        assert coll.observe.called

    def test_observe_wait_duration(self) -> None:
        coll = MagicMock()
        m = TenacityMetrics(collector=coll)
        m.observe_wait_duration(name="r1", duration=0.5)
        coll.observe.assert_called_once()
