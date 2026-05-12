from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable


@runtime_checkable
class MetricsCollector(Protocol):
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
    def serve(self) -> None: ...


@runtime_checkable
class RetryMetrics(Protocol):
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


@runtime_checkable
class CBMetrics(Protocol):
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


class CacheOperation:
    __slots__ = ("hit",)

    def __init__(self) -> None:
        self.hit: bool | None = None


@runtime_checkable
class CacheMetrics(Protocol):
    def track(self, operation: str) -> AbstractAsyncContextManager[CacheOperation]: ...
    def set_queue_size(self, queue_name: str, count: int) -> None: ...


@runtime_checkable
class DBMetrics(Protocol):
    def register(self, engine: object) -> None: ...


@runtime_checkable
class RLMetrics(Protocol):
    def before_call(self) -> None: ...
    def on_call(
        self,
        name: str,
        limit: str,
        result: bool,
    ) -> None: ...
    def on_get_stats(
        self,
        name: str,
        reset_time: float,
        remaining: int,
    ) -> None: ...
    def on_reset(self, name: str, limit: int) -> None: ...


@runtime_checkable
class MetricsRegistry(Protocol):
    """Протокол для регистрации метрик."""

    @property
    def retry_metrics(self) -> RetryMetrics: ...

    @property
    def cb_metrics(self) -> CBMetrics: ...

    @property
    def rl_metrics(self) -> RLMetrics: ...

    @property
    def cache_metrics(self) -> CacheMetrics: ...

    @property
    def db_metrics(self) -> DBMetrics: ...
