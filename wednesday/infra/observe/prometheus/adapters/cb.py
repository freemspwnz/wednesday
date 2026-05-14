"""Asyncbreaker metrics adapter."""

import time

from app.protocols import CBMetrics, MetricsCollector

from ._common import TimerContext

_STATE_VALUES: dict[str, float] = {
    "CLOSED": 0.0,
    "HALF_OPEN": 0.5,
    "OPEN": 1.0,
}
_UNKNOWN_STATE_VALUE = -1.0


class AsyncbreakerMetrics(CBMetrics):
    """Адаптер метрик для asyncbreaker."""

    def __init__(self, *, collector: MetricsCollector) -> None:
        self._collector = collector
        self._call_timer = TimerContext("_cb_call_timer")
        self._state_started: dict[str, float] = {}

    def before_call(self) -> None:
        self._call_timer.start()

    def after_call(self, name: str, result: str) -> None:
        labels = {"name": name, "result": result}
        self._collector.observe(
            name="cb_call_duration_seconds",
            value=self._call_timer.elapsed(),
            labels=labels,
        )
        self._collector.increment(name="cb_calls_total", labels=labels)

    def on_state_change(self, name: str, old_state: str, new_state: str) -> None:
        now = time.monotonic()
        started = self._state_started.get(name)
        duration = (now - started) if started is not None else 0.0
        self._state_started[name] = now

        self._collector.set_gauge(
            name="cb_state",
            value=self._map_state(new_state),
            labels={"name": name},
        )
        self._collector.increment(
            name="cb_state_transitions_total",
            labels={"name": name, "old_state": old_state, "new_state": new_state},
        )
        self._collector.observe(
            name="cb_state_duration_seconds",
            value=duration,
            labels={"name": name, "state": old_state},
        )

    @staticmethod
    def _map_state(state: str) -> float:
        return _STATE_VALUES.get(state, _UNKNOWN_STATE_VALUE)
