"""Limits rate-limiter metrics adapter."""

from app.protocols import MetricsCollector, RLMetrics

from ._common import TimerContext


class LimitsMetrics(RLMetrics):
    """Metrics adapter for the limits rate limiter."""

    def __init__(self, *, collector: MetricsCollector) -> None:
        self._collector = collector
        self._call_timer = TimerContext("_rl_call_timer")

    def before_call(self) -> None:
        self._call_timer.start()

    def on_call(self, *, limiter: str, bucket: str, limit: str, result: bool) -> None:
        labels = {"limiter": limiter, "bucket": bucket}
        self._collector.observe(
            name="rl_calls_duration_seconds",
            value=self._call_timer.elapsed(),
            labels=labels,
        )
        self._collector.increment(
            name="rl_calls_total",
            labels={
                **labels,
                "limit": limit,
                "result": "success" if result else "failure",
            },
        )

    def on_error(self, *, limiter: str, bucket: str, operation: str, error: str) -> None:
        if operation == "get_stats":
            duration_metric = "rl_window_stats_duration_seconds"
        elif operation == "reset":
            duration_metric = "rl_resets_duration_seconds"
        else:
            duration_metric = "rl_calls_duration_seconds"
        labels = {"limiter": limiter, "bucket": bucket}
        self._collector.observe(
            name=duration_metric,
            value=self._call_timer.elapsed(),
            labels=labels,
        )
        self._collector.increment(
            name="rl_errors_total",
            labels={**labels, "operation": operation, "error": error},
        )

    def on_get_stats(
        self,
        *,
        limiter: str,
        bucket: str,
        reset_time: float,
        remaining: int,
    ) -> None:
        labels = {"limiter": limiter, "bucket": bucket}
        self._collector.observe(
            name="rl_window_stats_duration_seconds",
            value=self._call_timer.elapsed(),
            labels=labels,
        )
        self._collector.set_gauge(
            name="rl_window_stats_remaining",
            value=remaining,
            labels=labels,
        )
        self._collector.set_gauge(
            name="rl_window_stats_reset_timestamp_seconds",
            value=reset_time,
            labels=labels,
        )
        self._collector.increment(
            name="rl_window_stats_calls_total",
            labels={**labels, "result": "success"},
        )

    def on_reset(self, *, limiter: str, bucket: str, limit: int) -> None:
        labels = {"limiter": limiter, "bucket": bucket}
        self._collector.observe(
            name="rl_resets_duration_seconds",
            value=self._call_timer.elapsed(),
            labels=labels,
        )
        self._collector.set_gauge(
            name="rl_window_stats_remaining",
            value=float(limit),
            labels=labels,
        )
        self._collector.set_gauge(
            name="rl_window_stats_reset_timestamp_seconds",
            value=0.0,
            labels=labels,
        )
        self._collector.increment(
            name="rl_reset_calls_total",
            labels=labels,
        )
