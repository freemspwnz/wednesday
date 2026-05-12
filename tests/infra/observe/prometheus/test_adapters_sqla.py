"""Тесты SQLAMetrics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text

from infra.observe.prometheus.adapters.sqla import SQLAMetrics
from infra.observe.prometheus.client import PrometheusCollector


@pytest.mark.unit
class TestSQLAMetricsExtractCommand:
    def test_empty(self) -> None:
        assert SQLAMetrics._extract_command("") == "unknown"

    def test_select(self) -> None:
        assert SQLAMetrics._extract_command("  SeLeCt 1") == "SELECT"

    def test_no_match(self) -> None:
        assert SQLAMetrics._extract_command("%%%") == "unknown"


@pytest.mark.unit
class TestSQLAMetricsRegister:
    def test_register_rejects_non_engine(self) -> None:
        m = SQLAMetrics(collector=MagicMock())
        with pytest.raises(TypeError, match="Engine"):
            m.register(object())

    def test_successful_query_emits_metrics(self, collector: PrometheusCollector) -> None:
        m = SQLAMetrics(collector=collector)
        engine = create_engine("sqlite:///:memory:")
        m.register(engine)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        out = collector.export().decode()
        assert "sqlalchemy" in out.lower()
        engine.dispose()

    def test_after_without_before_no_crash(self, collector: PrometheusCollector) -> None:
        m = SQLAMetrics(collector=collector)
        engine = create_engine("sqlite:///:memory:")
        m.register(engine)

        class _Ctx:
            pass

        ctx = _Ctx()
        m._after_cursor_execute(None, None, "SELECT 1", None, ctx, False)
        engine.dispose()

    def test_handle_error_increments(self) -> None:
        coll = MagicMock()
        m = SQLAMetrics(collector=coll)

        class _Err(Exception):
            pass

        exc_ctx = MagicMock()
        exc_ctx.statement = "UPDATE t SET x = 1"
        exc_ctx.original_exception = _Err()

        m._handle_error(exc_ctx)
        coll.increment.assert_called_once()
        kwargs = coll.increment.call_args.kwargs
        assert kwargs["name"] == "sqlalchemy_errors_total"
        assert kwargs["labels"]["command"] == "UPDATE"
        assert kwargs["labels"]["error_type"] == "_Err"
