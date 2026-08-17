from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable


@runtime_checkable
class MetricsCollector(Protocol):
    """Protocol for metrics collection."""

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


@runtime_checkable
class RetryMetrics(Protocol):
    """Protocol for retry metrics collection."""

    def before_retry(self) -> None: ...
    def after_retry(
        self,
        *,
        name: str,
    ) -> None: ...
    def on_retry(
        self,
        *,
        name: str,
        attempt: int,
        status: str,
    ) -> None: ...
    def observe_wait_duration(
        self,
        *,
        name: str,
        duration: float,
    ) -> None: ...


@runtime_checkable
class CBMetrics(Protocol):
    """Protocol for circuit breaker metrics collection."""

    def before_call(self) -> None: ...
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
    """Cache operation result."""

    __slots__ = ("hit",)

    def __init__(self) -> None:
        self.hit: bool | None = None


@runtime_checkable
class CacheMetrics(Protocol):
    """Protocol for cache metrics collection."""

    def track(self, operation: str) -> AbstractAsyncContextManager[CacheOperation]: ...
    def set_queue_size(self, queue_name: str, count: int) -> None: ...


@runtime_checkable
class DBMetrics(Protocol):
    """Protocol for database metrics collection."""

    def on_before_cursor_execute(  # noqa: PLR0913, PLR0917
        self,
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None: ...

    def on_after_cursor_execute(  # noqa: PLR0913, PLR0917
        self,
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None: ...

    def on_cursor_error(
        self,
        *,
        statement: str,
        error_type: str,
        context: object | None = None,
    ) -> None: ...


@runtime_checkable
class RLMetrics(Protocol):
    """Protocol for rate limiter metrics collection."""

    def before_call(self) -> None: ...
    def on_call(self, *, limiter: str, bucket: str, limit: str, result: bool) -> None: ...
    def on_get_stats(self, *, limiter: str, bucket: str, reset_time: float, remaining: int) -> None: ...
    def on_error(self, *, limiter: str, bucket: str, operation: str, error: str) -> None: ...
    def on_reset(self, *, limiter: str, bucket: str, limit: int) -> None: ...


@runtime_checkable
class HttpMetrics(Protocol):
    """Protocol for HTTP metrics collection."""

    def on_request(self, *, method: str, url: str) -> None: ...

    def on_response(self, *, method: str, url: str, status_code: int) -> None: ...

    def on_error(self, *, method: str, url: str, exc: BaseException) -> None: ...


@runtime_checkable
class MetricsRegistry(Protocol):
    """Protocol for metrics registration."""

    @property
    def retry(self) -> RetryMetrics: ...

    @property
    def cb(self) -> CBMetrics: ...

    @property
    def rl(self) -> RLMetrics: ...

    @property
    def cache(self) -> CacheMetrics: ...

    @property
    def db(self) -> DBMetrics: ...

    @property
    def http(self) -> HttpMetrics: ...

    def serve(self) -> None: ...
