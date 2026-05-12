"""Limits rate-limiter metrics adapter."""

from app.protocols import MetricsCollector, RLMetrics

from ._common import TimerContext


class LimitsMetrics(RLMetrics):
    """Адаптер метрик для limits."""

    def __init__(self, *, collector: MetricsCollector) -> None:
        self._collector = collector
        self._call_timer = TimerContext("_rl_call_timer")

    def before_call(self) -> None:
        self._call_timer.start()

    def on_call(self, name: str, limit: str, result: bool) -> None:
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

    def on_get_stats(
        self,
        name: str,
        reset_time: float | None = None,
        remaining: int | None = None,
    ) -> None:
        self._collector.observe(
            name="rl_window_stats_duration_seconds",
            value=self._call_timer.elapsed(),
            labels={"name": name},
        )

        if remaining is not None and reset_time is not None:
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
            return

        self._collector.increment(
            name="rl_window_stats_calls_total",
            labels={"name": name, "result": "failure"},
        )

    def on_reset(self, name: str, limit: int) -> None:
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
