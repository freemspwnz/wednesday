"""Prometheus-реализация MetricsCollector + HTTP-экспортёр."""

from collections.abc import Mapping
from typing import TypeVar

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    start_http_server,
)

from app.exceptions import PrometheusExportError, PrometheusHttpExporterError
from app.protocols import Logger, MetricsCollector
from infra.config import MetricsConfig

_NAMESPACE = "wednesday"
_M = TypeVar("_M", Counter, Gauge, Histogram)


class PrometheusCollector(MetricsCollector):
    """Pull-модель сбора метрик через prometheus_client."""

    def __init__(
        self,
        *,
        config: MetricsConfig,
        env: str,
        version: str,
        registry: CollectorRegistry,
        logger: Logger,
    ) -> None:
        self._config = config
        self._registry = registry
        self._counters: dict[str, Counter] = {}
        self._histograms: dict[str, Histogram] = {}
        self._gauges: dict[str, Gauge] = {}
        self._logger = logger.bind(module=self.__class__.__name__)
        self._register_build_info(env=env, version=version)

    def increment(self, *, name: str, labels: dict[str, str]) -> None:
        counter = self._get_or_create(self._counters, name, labels, Counter)
        if labels:
            counter.labels(**labels).inc()
        else:
            counter.inc()

    def observe(self, *, name: str, value: float, labels: dict[str, str]) -> None:
        histogram = self._get_or_create(self._histograms, name, labels, Histogram)
        if labels:
            histogram.labels(**labels).observe(value)
        else:
            histogram.observe(value)

    def set_gauge(self, *, name: str, value: float, labels: dict[str, str]) -> None:
        gauge = self._get_or_create(self._gauges, name, labels, Gauge)
        if labels:
            gauge.labels(**labels).set(value)
        else:
            gauge.set(value)

    def export(self) -> bytes:
        try:
            return generate_latest(self._registry)
        except Exception as e:
            self._logger.exception("Prometheus export failed")
            raise PrometheusExportError("Prometheus export failed") from e

    def serve(self) -> None:
        if not self._config.enabled:
            self._logger.info("Prometheus HTTP exporter disabled by config")
            return
        try:
            start_http_server(
                addr=self._config.host,
                port=self._config.port,
                registry=self._registry,
            )
        except Exception as e:
            self._logger.exception(
                "Prometheus HTTP exporter failed to start",
                host=self._config.host,
                port=self._config.port,
            )
            raise PrometheusHttpExporterError("Prometheus HTTP exporter failed to start") from e
        self._logger.info(f"Prometheus HTTP exporter started on {self._config.host}:{self._config.port}")

    def _get_or_create(
        self,
        cache: dict[str, _M],
        name: str,
        labels: Mapping[str, str] | None,
        factory: type[_M],
    ) -> _M:
        metric = cache.get(name)
        if metric is not None:
            return metric
        labelnames = tuple(sorted(labels.keys())) if labels else ()
        metric = factory(
            name,
            f"{factory.__name__} {name}",
            labelnames=labelnames,
            namespace=_NAMESPACE,
            registry=self._registry,
        )
        cache[name] = metric
        self._logger.debug(f"{factory.__name__} {name} created")
        return metric

    def _register_build_info(self, *, env: str, version: str) -> None:
        info = Info(
            "build",
            "Wednesday build / runtime metadata",
            namespace=_NAMESPACE,
            registry=self._registry,
        )
        info.info({"env": env, "version": version})
