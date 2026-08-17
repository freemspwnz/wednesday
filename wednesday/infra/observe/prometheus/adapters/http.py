"""Outbound HTTP metrics adapter (library-agnostic)."""

from typing import ClassVar
from urllib.parse import urlparse

from app.protocols import HttpMetrics, MetricsCollector

from ._common import TimerContext


class HttpxMetrics(HttpMetrics):
    """Outbound HTTP metrics adapter."""

    _PREFIX: ClassVar[str] = "http"
    _TIMEOUT_TYPE_NAMES: ClassVar[frozenset[str]] = frozenset({
        "TimeoutException",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
    })

    def __init__(self, *, collector: MetricsCollector) -> None:
        self._collector = collector
        self._timer = TimerContext("_http_call_timer")

    def on_request(self, *, method: str, url: str) -> None:
        self._timer.start()

    def on_response(self, *, method: str, url: str, status_code: int) -> None:
        self._emit(
            method=method,
            url=url,
            outcome="success",
            status_code=status_code,
        )

    def on_error(self, *, method: str, url: str, exc: BaseException) -> None:
        outcome, status_code = self._classify_error(exc)
        self._emit(
            method=method,
            url=url,
            outcome=outcome,
            status_code=status_code,
        )

    def _emit(self, *, method: str, url: str, outcome: str, status_code: int) -> None:
        labels = {
            "method": method.upper(),
            "url": self._normalize_url(url),
            "outcome": outcome,
            "status_code": str(status_code),
        }
        self._collector.observe(
            name=f"{self._PREFIX}_request_duration_seconds",
            value=self._timer.elapsed(),
            labels=labels,
        )
        self._collector.increment(
            name=f"{self._PREFIX}_requests_total",
            labels=labels,
        )

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    @staticmethod
    def _classify_error(exc: BaseException) -> tuple[str, int]:
        status_code = HttpxMetrics._status_code_from_exception(exc)
        if status_code is not None:
            return "http_error", status_code

        if HttpxMetrics._is_timeout_error(exc) or type(exc).__name__ == "HttpTimeoutError":
            return "timeout", 0

        if HttpxMetrics._is_transport_error(exc) or type(exc).__name__ == "HttpTransportError":
            return "connection_error", 0

        return "error", 0

    @staticmethod
    def _status_code_from_exception(exc: BaseException) -> int | None:
        direct = getattr(exc, "status_code", None)
        if direct is not None:
            return int(direct)

        response = getattr(exc, "response", None)
        if response is None:
            return None
        status_code = getattr(response, "status_code", None)
        if status_code is None:
            return None
        return int(status_code)

    @classmethod
    def _is_timeout_error(cls, exc: BaseException) -> bool:
        names = cls._TIMEOUT_TYPE_NAMES
        return any(mro_cls.__name__ in names for mro_cls in type(exc).__mro__)

    @staticmethod
    def _is_transport_error(exc: BaseException) -> bool:
        return any(mro_cls.__name__ == "TransportError" for mro_cls in type(exc).__mro__)
