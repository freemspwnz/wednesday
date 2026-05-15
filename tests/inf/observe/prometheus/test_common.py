"""Тесты TimerContext (adapters._common)."""

from __future__ import annotations

import asyncio

import pytest

from infra.observe.prometheus.adapters._common import TimerContext


@pytest.mark.unit
class TestTimerContext:
    def test_elapsed_without_start_returns_zero(self) -> None:
        t = TimerContext("test_timer_ctx_zero")
        assert t.elapsed() == 0.0

    def test_elapsed_after_start_is_non_negative(self) -> None:
        t = TimerContext("test_timer_ctx_mono")
        t.start()
        assert t.elapsed() >= 0.0

    @pytest.mark.asyncio
    async def test_tasks_have_independent_context(self) -> None:
        t = TimerContext("test_timer_ctx_async")

        async def task_a() -> float:
            t.start()
            await asyncio.sleep(0.01)
            return t.elapsed()

        async def task_b() -> None:
            await asyncio.sleep(0.005)
            t.start()

        a_elapsed, _ = await asyncio.gather(task_a(), task_b())
        assert a_elapsed >= 0.009
