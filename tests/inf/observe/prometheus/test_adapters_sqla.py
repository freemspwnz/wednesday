"""Тесты SQLAMetrics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infra.observe.prometheus.adapters.sqla import SQLAMetrics
from infra.observe.prometheus.collector import PrometheusCollector


class _Ctx:
    """Stand-in for SQLAlchemy execution context (must be weakref-able)."""


@pytest.mark.unit
class TestSQLAMetricsExtractCommand:
    def test_empty(self) -> None:
        assert SQLAMetrics._extract_command("") == "unknown"

    def test_select(self) -> None:
        assert SQLAMetrics._extract_command("  SeLeCt 1") == "SELECT"

    def test_no_match(self) -> None:
        assert SQLAMetrics._extract_command("%%%") == "unknown"


@pytest.mark.unit
class TestSQLAMetricsCursorHooks:
    def test_after_without_before_does_not_emit(self) -> None:
        coll = MagicMock()
        m = SQLAMetrics(collector=coll)
        ctx = _Ctx()

        m.on_after_cursor_execute(context=ctx, statement="SELECT 1")

        coll.observe.assert_not_called()
        coll.increment.assert_not_called()

    def test_success_path_emits_metrics(self) -> None:
        coll = MagicMock()
        m = SQLAMetrics(collector=coll)
        ctx = _Ctx()

        m.on_before_cursor_execute(context=ctx, statement="SELECT 1")
        m.on_after_cursor_execute(context=ctx, statement="select 1")

        coll.observe.assert_called_once()
        assert coll.observe.call_args.kwargs["name"] == "sqlalchemy_query_duration_seconds"
        assert coll.observe.call_args.kwargs["labels"] == {"command": "SELECT"}

        coll.increment.assert_called_once()
        assert coll.increment.call_args.kwargs["name"] == "sqlalchemy_queries_total"
        assert coll.increment.call_args.kwargs["labels"] == {
            "command": "SELECT",
            "status": "success",
        }

    def test_on_cursor_error_increments(self) -> None:
        coll = MagicMock()
        m = SQLAMetrics(collector=coll)

        m.on_cursor_error(statement="UPDATE t SET x = 1", error_type="IntegrityError")

        coll.increment.assert_called_once()
        kwargs = coll.increment.call_args.kwargs
        assert kwargs["name"] == "sqlalchemy_errors_total"
        assert kwargs["labels"]["command"] == "UPDATE"
        assert kwargs["labels"]["error_type"] == "IntegrityError"
        coll.observe.assert_not_called()

    def test_on_cursor_error_clears_pending_start(self) -> None:
        coll = MagicMock()
        m = SQLAMetrics(collector=coll)
        ctx = _Ctx()

        m.on_before_cursor_execute(context=ctx, statement="SELECT 1")
        m.on_cursor_error(statement="SELECT 1", error_type="OperationalError", context=ctx)
        m.on_after_cursor_execute(context=ctx, statement="SELECT 1")

        coll.increment.assert_called_once()
        coll.observe.assert_not_called()


@pytest.mark.unit
class TestSQLAMetricsEngineIntegration:
    def test_attach_engine_metrics_emits_on_query(self, collector: PrometheusCollector) -> None:
        from sqlalchemy import create_engine as create_sync_engine, text

        from infra.persistence.sqlalchemy.factory import _attach_engine_metrics

        metrics = SQLAMetrics(collector=collector)
        engine = create_sync_engine("sqlite:///:memory:")
        _attach_engine_metrics(engine, metrics)

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        out = collector.export().decode()
        assert "sqlalchemy_query_duration_seconds" in out
        assert "sqlalchemy_queries_total" in out
        engine.dispose()
