from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import NamedTuple, Protocol


class IMetricsCollector(Protocol):
    """Протокол для сбора метрик."""

    def increment(
        self,
        *,
        name: str,
        labels: dict[str, str],
    ) -> None: ...

    def observe(
        self,
        *,
        name: str,
        value: float,
        labels: dict[str, str],
    ) -> None: ...

    def set_gauge(
        self,
        *,
        name: str,
        value: float,
        labels: dict[str, str],
    ) -> None: ...

    def export(self) -> bytes: ...


class IRetryMetrics(Protocol):
    def before_retry(self) -> None: ...
    def after_retry(
        self,
        *,
        name: str,
        method: str,
    ) -> None: ...
    def on_retry(
        self,
        *,
        name: str,
        method: str,
        attempt: int,
        status: str,
    ) -> None: ...
    def observe_wait_duration(
        self,
        *,
        name: str,
        method: str,
        duration: float,
    ) -> None: ...


class ICBMetrics(Protocol):
    def before_call(self, method: str) -> None: ...
    def after_call(
        self,
        name: str,
        result: str,
    ) -> None: ...
    def on_state_change(
        self,
        name: str,
        old_state: str,
        new_state: str,
    ) -> None: ...


class ICacheMetrics(Protocol):
    def track(self, operation: str) -> AsyncGenerator: ...
    def set_queue_size(self, queue_name: str, count: int) -> None: ...


class ISQLAMetrics(Protocol):
    def register(self, engine: object) -> None: ...


class IRLMetrics(Protocol):
    def before_call(self) -> None: ...
    def on_call(
        self,
        name: str,
        limit: str,
        result: bool,
    ) -> None: ...
    def on_get_stats(self, name: str, stats: NamedTuple | None) -> None: ...
    def on_reset(self, name: str) -> None: ...


class IMetricsRegistry(Protocol):
    """Протокол для регистрации метрик."""

    @property
    def retry_metrics(self) -> IRetryMetrics: ...

    @property
    def cb_metrics(self) -> ICBMetrics: ...

    @property
    def rl_metrics(self) -> IRLMetrics: ...

    @property
    def cache_metrics(self) -> ICacheMetrics: ...

    @property
    def sqla_metrics(self) -> ISQLAMetrics: ...
