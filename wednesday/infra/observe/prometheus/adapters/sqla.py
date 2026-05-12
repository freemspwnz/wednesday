"""SQLAlchemy metrics adapter."""

import re
import time
import weakref
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import ExceptionContext

from app.protocols import DBMetrics, MetricsCollector

_COMMAND_RE = re.compile(r"^\s*(\w+)", re.IGNORECASE)


class SQLAMetrics(DBMetrics):
    """Адаптер метрик для SQLAlchemy."""

    def __init__(self, *, collector: MetricsCollector) -> None:
        self._collector = collector
        self._start_times: weakref.WeakKeyDictionary[Any, float] = weakref.WeakKeyDictionary()

    def register(self, engine: object) -> None:
        if not isinstance(engine, Engine):
            raise TypeError(f"Expected sqlalchemy.engine.Engine, got {type(engine).__name__}")
        event.listen(engine, "before_cursor_execute", self._before_cursor_execute)
        event.listen(engine, "after_cursor_execute", self._after_cursor_execute)
        event.listen(engine, "handle_error", self._handle_error)

    def _before_cursor_execute(  # noqa: PLR0913, PLR0917
        self,
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        self._start_times[context] = time.perf_counter()

    def _after_cursor_execute(  # noqa: PLR0913, PLR0917
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
        duration = time.perf_counter() - start
        command = self._extract_command(statement)
        self._collector.observe(
            name="sqlalchemy_query_duration_seconds",
            value=duration,
            labels={"command": command},
        )
        self._collector.increment(
            name="sqlalchemy_queries_total",
            labels={"command": command, "status": "success"},
        )

    def _handle_error(self, exception_context: ExceptionContext) -> None:
        command = self._extract_command(exception_context.statement or "")
        self._collector.increment(
            name="sqlalchemy_errors_total",
            labels={
                "command": command,
                "error_type": type(exception_context.original_exception).__name__,
            },
        )

    @staticmethod
    def _extract_command(statement: str) -> str:
        if not statement:
            return "unknown"
        match = _COMMAND_RE.match(statement)
        return match.group(1).upper() if match else "unknown"
