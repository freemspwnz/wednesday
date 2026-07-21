"""Prometheus registry — facade over per-typed adapters."""

from functools import cached_property

from prometheus_client import CollectorRegistry, start_http_server

from app.exceptions import MetricsHttpExporterError
from app.protocols import (
    CacheMetrics,
    CBMetrics,
    DBMetrics,
    HttpMetrics,
    Logger,
    MetricsCollector,
    MetricsRegistry,
    RetryMetrics,
    RLMetrics,
)
from infra.config import MetricsConfig

from .adapters import (
    AsyncbreakerMetrics,
    HttpxMetrics,
    LimitsMetrics,
    RedisMetrics,
    SQLAMetrics,
    TenacityMetrics,
)
from .collector import PrometheusCollector


class PrometheusRegistry(MetricsRegistry):
    """Metrics infrastructure adapters registry."""

    def __init__(
        self,
        *,
        config: MetricsConfig,
        env: str,
        version: str,
        logger: Logger,
    ) -> None:
        self._config = config
        self._env = env
        self._version = version
        self._registry = CollectorRegistry()
        self._logger = logger.bind(module=self.__class__.__name__)

    @cached_property
    def retry(self) -> RetryMetrics:
        return TenacityMetrics(collector=self._collector)

    @cached_property
    def cb(self) -> CBMetrics:
        return AsyncbreakerMetrics(collector=self._collector)

    @cached_property
    def cache(self) -> CacheMetrics:
        return RedisMetrics(collector=self._collector)

    @cached_property
    def db(self) -> DBMetrics:
        return SQLAMetrics(collector=self._collector)

    @cached_property
    def rl(self) -> RLMetrics:
        return LimitsMetrics(collector=self._collector)

    @cached_property
    def http(self) -> HttpMetrics:
        return HttpxMetrics(collector=self._collector)

    @cached_property
    def _collector(self) -> MetricsCollector:
        return PrometheusCollector(
            config=self._config,
            env=self._env,
            version=self._version,
            registry=self._registry,
            logger=self._logger,
        )

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
            raise MetricsHttpExporterError("Prometheus HTTP exporter failed to start") from e
        self._logger.info(f"Prometheus HTTP exporter started on {self._config.host}:{self._config.port}")
