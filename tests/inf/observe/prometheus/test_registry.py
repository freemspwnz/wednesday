"""PrometheusRegistry tests."""

from unittest.mock import MagicMock, patch

import pytest
from prometheus_client import CollectorRegistry

from app.exceptions import MetricsHttpExporterError
from infra.config import MetricsConfig
from infra.observe.prometheus import PrometheusRegistry
from infra.observe.prometheus.adapters import (
    AsyncbreakerMetrics,
    HttpxMetrics,
    LimitsMetrics,
    RedisMetrics,
    SQLAMetrics,
    TenacityMetrics,
)


@pytest.fixture
def prometheus_registry(
    metrics_config: MetricsConfig,
    mock_logger: MagicMock,
) -> PrometheusRegistry:
    return PrometheusRegistry(
        config=metrics_config,
        env="TEST",
        version="0.0.1",
        logger=mock_logger,
    )


@pytest.mark.unit
class TestPrometheusRegistry:
    def test_properties_return_singletons(self, prometheus_registry: PrometheusRegistry) -> None:
        reg = prometheus_registry

        assert isinstance(reg.retry, TenacityMetrics)
        assert isinstance(reg.cb, AsyncbreakerMetrics)
        assert isinstance(reg.cache, RedisMetrics)
        assert isinstance(reg.db, SQLAMetrics)
        assert isinstance(reg.rl, LimitsMetrics)
        assert isinstance(reg.http, HttpxMetrics)

        assert reg.retry is reg.retry
        assert reg.cb is reg.cb
        assert reg.http is reg.http

    def test_adapters_share_collector(self, prometheus_registry: PrometheusRegistry) -> None:
        reg = prometheus_registry
        assert isinstance(reg.retry, TenacityMetrics)
        assert isinstance(reg.cb, AsyncbreakerMetrics)
        assert isinstance(reg.http, HttpxMetrics)
        assert reg.retry._collector is reg._collector
        assert reg.cb._collector is reg._collector
        assert reg.http._collector is reg._collector

    def test_serve_disabled_logs_info(
        self,
        metrics_config: MetricsConfig,
        mock_logger: MagicMock,
    ) -> None:
        reg = PrometheusRegistry(
            config=metrics_config.model_copy(update={"enabled": False}),
            env="X",
            version="1",
            logger=mock_logger,
        )
        reg.serve()
        mock_logger.info.assert_called()
        assert "disabled" in str(mock_logger.info.call_args).lower()

    def test_serve_enabled_starts_server(self, mock_logger: MagicMock) -> None:
        cfg = MetricsConfig(enabled=True, host="127.0.0.1", port=9123)
        reg = PrometheusRegistry(config=cfg, env="X", version="1", logger=mock_logger)
        with patch("infra.observe.prometheus.registry.start_http_server") as srv:
            reg.serve()
        srv.assert_called_once()
        kwargs = srv.call_args.kwargs
        assert kwargs["addr"] == "127.0.0.1"
        assert kwargs["port"] == 9123
        assert isinstance(kwargs["registry"], CollectorRegistry)
        mock_logger.info.assert_called()

    def test_serve_bind_failure_logs_exception(self, mock_logger: MagicMock) -> None:
        cfg = MetricsConfig(enabled=True, host="127.0.0.1", port=9124)
        reg = PrometheusRegistry(config=cfg, env="X", version="1", logger=mock_logger)
        with patch(
            "infra.observe.prometheus.registry.start_http_server",
            side_effect=OSError("bind failed"),
        ):
            with pytest.raises(MetricsHttpExporterError):
                reg.serve()
        mock_logger.exception.assert_called()

    def test_serve_non_os_error_logs_exception(self, mock_logger: MagicMock) -> None:
        cfg = MetricsConfig(enabled=True, host="127.0.0.1", port=9125)
        reg = PrometheusRegistry(config=cfg, env="X", version="1", logger=mock_logger)
        with patch(
            "infra.observe.prometheus.registry.start_http_server",
            side_effect=RuntimeError("unexpected"),
        ):
            with pytest.raises(MetricsHttpExporterError):
                reg.serve()
        mock_logger.exception.assert_called()
