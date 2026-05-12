"""Общие утилиты для prometheus-адаптеров."""

import time
from contextvars import ContextVar


class TimerContext:
    """ContextVar-timer for measuring duration of per-call.

    Semantics based on PEP 567: each asyncio task has its own copy of the context,
    so `before_*` and `after_*`, called inside one task, see the same value.

    Correctly works in the typical aiogram flow
    (one update — one task, middleware and handler share the context).

    Known limitation: explicit `asyncio.create_task(...)` or `gather(...)`
    between `before_*` and `after_*` produces a child task
    with an independent copy of the context — `elapsed()` in the parent
    after such will return the value **from its own** `start()`, and the child — from its own.
    The current resilience wrappers do not do this.
    """

    __slots__ = ("_var",)

    def __init__(self, var_name: str) -> None:
        self._var: ContextVar[float | None] = ContextVar(var_name, default=None)

    def start(self) -> None:
        self._var.set(time.monotonic())

    def elapsed(self) -> float:
        """Секунды с момента `start()` или 0.0, если не вызывался."""
        started = self._var.get()
        if started is None:
            return 0.0
        return time.monotonic() - started
