"""SQLAlchemy query metrics adapter (timing + Prometheus; no sqlalchemy import)."""

import re
import time
import weakref
from typing import Any, ClassVar

from app.protocols import DBMetrics, MetricsCollector


class SQLAMetrics(DBMetrics):
    """SQLAlchemy query metrics adapter."""

    _PREFIX: ClassVar[str] = "sqlalchemy"
    _COMMAND_RE: ClassVar[re.Pattern[str]] = re.compile(r"^\s*(\w+)", re.IGNORECASE)

    def __init__(self, *, collector: MetricsCollector) -> None:
        self._collector = collector
        self._start_times: weakref.WeakKeyDictionary[Any, float] = weakref.WeakKeyDictionary()

    def on_before_cursor_execute(  # noqa: PLR0913, PLR0917
        self,
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        self._start_times[context] = time.perf_counter()

    def on_after_cursor_execute(  # noqa: PLR0913, PLR0917
        self,
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
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

    @classmethod
    def _extract_command(cls, statement: str) -> str:
        if not statement:
            return "unknown"
        match = cls._COMMAND_RE.match(statement)
        return match.group(1).upper() if match else "unknown"

    def _emit_success(self, *, command: str, duration_seconds: float) -> None:
        labels = {"command": command}
        self._collector.observe(
            name=f"{self._PREFIX}_query_duration_seconds",
            value=duration_seconds,
            labels=labels,
        )
        self._collector.increment(
            name=f"{self._PREFIX}_queries_total",
            labels={**labels, "status": "success"},
        )

    def _emit_error(self, *, command: str, error_type: str) -> None:
        self._collector.increment(
            name=f"{self._PREFIX}_errors_total",
            labels={"command": command, "error_type": error_type},
        )
