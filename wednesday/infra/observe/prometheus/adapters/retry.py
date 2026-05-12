"""Tenacity retry metrics adapter."""

from app.protocols import MetricsCollector, RetryMetrics

from ._common import TimerContext


class TenacityMetrics(RetryMetrics):
    """Адаптер метрик для tenacity."""

    def __init__(self, *, collector: MetricsCollector) -> None:
        self._collector = collector
        self._call_timer = TimerContext("_retry_call_timer")

    def before_retry(self) -> None:
        self._call_timer.start()

    def after_retry(self, *, name: str, method: str) -> None:
        self._collector.observe(
            name="retry_call_duration_seconds",
            value=self._call_timer.elapsed(),
            labels={"name": name, "method": method},
        )

    def on_retry(self, *, name: str, method: str, attempt: int, status: str) -> None:
        common = {"name": name, "method": method, "status": status}
        self._collector.increment(name="retry_attempts_total", labels=common)
        self._collector.observe(
            name="retry_attempt_number",
            value=float(attempt),
            labels=common,
        )

    def observe_wait_duration(self, *, name: str, method: str, duration: float) -> None:
        self._collector.observe(
            name="retry_wait_duration_seconds",
            value=duration,
            labels={"name": name, "method": method},
        )
