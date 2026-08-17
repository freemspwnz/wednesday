"""Prometheus implementation of MetricsCollector."""

from collections.abc import Mapping
from typing import ClassVar, TypeVar

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

from app.exceptions import MetricsExportError
from app.protocols import Logger, MetricsCollector
from infra.config import MetricsConfig

_M = TypeVar("_M", Counter, Gauge, Histogram)


class PrometheusCollector(MetricsCollector):
    """Pull-modeled metrics collector on prometheus_client library."""

    _NAMESPACE: ClassVar[str] = "wednesday"

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
        self._register_build_info(env=env, version=version)
        self._logger = logger.bind(module=self.__class__.__name__)

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
            raise MetricsExportError("Prometheus export failed") from e

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
            namespace=self._NAMESPACE,
            registry=self._registry,
        )
        cache[name] = metric
        self._logger.debug(f"{factory.__name__} {name} created")
        return metric

    def _register_build_info(self, *, env: str, version: str) -> None:
        info = Info(
            "build",
            "Wednesday build / runtime metadata",
            namespace=self._NAMESPACE,
            registry=self._registry,
        )
        info.info({"env": env, "version": version})
