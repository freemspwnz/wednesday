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

    def on_call(self, *, name: str, limit: str, result: bool) -> None:
        self._collector.observe(
            name="rl_calls_duration_seconds",
            value=self._call_timer.elapsed(),
            labels={"name": name},
        )
        self._collector.increment(
            name="rl_calls_total",
            labels={
                "name": name,
                "limit": limit,
                "result": "success" if result else "failure",
            },
        )

    def on_error(self, *, name: str, operation: str, error: str) -> None:
        if operation == "get_stats":
            duration_metric = "rl_window_stats_duration_seconds"
        elif operation == "reset":
            duration_metric = "rl_resets_duration_seconds"
        else:
            duration_metric = "rl_calls_duration_seconds"
        self._collector.observe(
            name=duration_metric,
            value=self._call_timer.elapsed(),
            labels={"name": name},
        )
        self._collector.increment(
            name="rl_errors_total",
            labels={"name": name, "operation": operation, "error": error},
        )

    def on_get_stats(
        self,
        *,
        name: str,
        reset_time: float,
        remaining: int,
    ) -> None:
        self._collector.observe(
            name="rl_window_stats_duration_seconds",
            value=self._call_timer.elapsed(),
            labels={"name": name},
        )
        self._collector.set_gauge(
            name="rl_window_stats_remaining",
            value=remaining,
            labels={"name": name},
        )
        self._collector.set_gauge(
            name="rl_window_stats_reset_timestamp_seconds",
            value=reset_time,
            labels={"name": name},
        )
        self._collector.increment(
            name="rl_window_stats_calls_total",
            labels={"name": name, "result": "success"},
        )

    def on_reset(self, *, name: str, limit: int) -> None:
        self._collector.observe(
            name="rl_resets_duration_seconds",
            value=self._call_timer.elapsed(),
            labels={"name": name},
        )
        self._collector.set_gauge(
            name="rl_window_stats_remaining",
            value=float(limit),
            labels={"name": name},
        )
        self._collector.set_gauge(
            name="rl_window_stats_reset_timestamp_seconds",
            value=0.0,
            labels={"name": name},
        )
        self._collector.increment(
            name="rl_reset_calls_total",
            labels={"name": name},
        )
