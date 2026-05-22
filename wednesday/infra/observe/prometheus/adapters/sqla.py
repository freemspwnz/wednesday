"""SQLAlchemy query metrics adapter (timing + Prometheus; no sqlalchemy import)."""

from __future__ import annotations

import re
import time
import weakref
from typing import Any

from app.protocols import DBMetrics, MetricsCollector

_PREFIX = "sqlalchemy"
_COMMAND_RE = re.compile(r"^\s*(\w+)", re.IGNORECASE)


class SQLAMetrics(DBMetrics):
    def __init__(self, *, collector: MetricsCollector) -> None:
        self._collector = collector
        self._start_times: weakref.WeakKeyDictionary[Any, float] = weakref.WeakKeyDictionary()

    def on_before_cursor_execute(self, *, context: object, statement: str) -> None:
        self._start_times[context] = time.perf_counter()

    def on_after_cursor_execute(self, *, context: object, statement: str) -> None:
        start = self._start_times.pop(context, None)
        if start is None:
            return
        self._emit_success(
            command=self._extract_command(statement),
            duration_seconds=time.perf_counter() - start,
        )

    def on_cursor_error(
        self,
        *,
        statement: str,
        error_type: str,
        context: object | None = None,
    ) -> None:
        if context is not None:
            self._start_times.pop(context, None)
        self._emit_error(command=self._extract_command(statement), error_type=error_type)

    @staticmethod
    def _extract_command(statement: str) -> str:
        if not statement:
            return "unknown"
        match = _COMMAND_RE.match(statement)
        return match.group(1).upper() if match else "unknown"

    def _emit_success(self, *, command: str, duration_seconds: float) -> None:
        labels = {"command": command}
        self._collector.observe(
            name=f"{_PREFIX}_query_duration_seconds",
            value=duration_seconds,
            labels=labels,
        )
        self._collector.increment(
            name=f"{_PREFIX}_queries_total",
            labels={**labels, "status": "success"},
        )

    def _emit_error(self, *, command: str, error_type: str) -> None:
        self._collector.increment(
            name=f"{_PREFIX}_errors_total",
            labels={"command": command, "error_type": error_type},
        )
