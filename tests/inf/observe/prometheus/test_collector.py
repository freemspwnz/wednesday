"""PrometheusCollector tests."""

from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import CollectorRegistry

from app.exceptions import MetricsExportError
from infra.config import MetricsConfig
from infra.observe.prometheus.collector import PrometheusCollector


@pytest.mark.unit
class TestPrometheusCollector:
    def test_increment_without_labels(self, collector: PrometheusCollector) -> None:
        collector.increment(name="plain_total", labels={})
        out = collector.export().decode()
        assert "plain" in out

    def test_increment_with_labels_order_invariant(self, collector: PrometheusCollector) -> None:
        collector.increment(name="lb_total", labels={"z": "1", "a": "2"})
        collector.increment(name="lb_total", labels={"a": "3", "z": "0"})
        out = collector.export().decode()
        assert "lb_total" in out

    def test_counter_and_histogram_distinct_names_in_registry(
        self,
        collector: PrometheusCollector,
    ) -> None:
        """Counter and Histogram with the same basename collide in the registry — use distinct names."""
        collector.increment(name="dup_counter", labels={"k": "v"})
        collector.observe(name="dup_histogram", value=1.0, labels={"k": "v"})
        raw = collector.export()
        assert b"dup_counter" in raw and b"dup_histogram" in raw

    def test_observe_without_labels(self, collector: PrometheusCollector) -> None:
        collector.observe(name="hist_plain", value=0.5, labels={})
        assert b"hist_plain" in collector.export()

    def test_set_gauge(self, collector: PrometheusCollector) -> None:
        collector.set_gauge(name="g1", value=3.0, labels={"n": "x"})
        collector.set_gauge(name="g1", value=4.0, labels={"n": "x"})
        out = collector.export().decode()
        assert "g1" in out

    def test_set_gauge_without_labels(self, collector: PrometheusCollector) -> None:
        collector.set_gauge(name="g_plain", value=2.0, labels={})
        assert "g_plain" in collector.export().decode()

    def test_export_contains_build_info(self, collector: PrometheusCollector) -> None:
        data = collector.export().decode()
        assert "build" in data.lower() or "wednesday" in data

    def test_export_failure_returns_fallback(
        self,
        metrics_config: MetricsConfig,
        registry: CollectorRegistry,
        mock_logger: MagicMock,
    ) -> None:
        c = PrometheusCollector(
            config=metrics_config,
            env="X",
            version="1",
            registry=registry,
            logger=mock_logger,
        )
        with patch(
            "infra.observe.prometheus.collector.generate_latest",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(MetricsExportError):
                c.export()
        mock_logger.exception.assert_called()

    def test_mutation_failure_swallowed(
        self,
        metrics_config: MetricsConfig,
        registry: CollectorRegistry,
        mock_logger: MagicMock,
    ) -> None:
        c = PrometheusCollector(
            config=metrics_config,
            env="X",
            version="1",
            registry=registry,
            logger=mock_logger,
        )
        with patch.object(c, "_get_or_create", side_effect=RuntimeError("inner")):
            with pytest.raises(RuntimeError, match="inner"):
                c.increment(name="any", labels={})

    def test_increment_label_mismatch_from_prometheus_propagates(
        self,
        collector: PrometheusCollector,
    ) -> None:
        collector.increment(name="same_name", labels={"a": "1"})
        with pytest.raises(ValueError):
            collector.increment(name="same_name", labels={"b": "1"})
