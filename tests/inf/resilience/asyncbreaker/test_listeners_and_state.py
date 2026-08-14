"""Tests for listeners and ``CircuitState`` in the asyncbreaker slice."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from asyncbreaker import CircuitState as LibState

from infra.resilience.asyncbreaker.listeners.logging import LoggingListener
from infra.resilience.asyncbreaker.listeners.metrics import MetricsListener
from infra.resilience.asyncbreaker.state import CircuitState


@pytest.mark.unit
class TestCircuitState:
    def test_from_library_closed(self) -> None:
        assert CircuitState.from_library(LibState.CLOSED) is CircuitState.CLOSED

    def test_from_library_open(self) -> None:
        assert CircuitState.from_library(LibState.OPEN) is CircuitState.OPEN

    def test_from_library_unknown_maps_to_unknown(self) -> None:
        unknown = SimpleNamespace(name="NOT_A_REAL_STATE")
        assert CircuitState.from_library(unknown) is CircuitState.UNKNOWN  # type: ignore[arg-type]

    def test_str_is_lower_name(self) -> None:
        assert str(CircuitState.HALF_OPEN) == "half_open"


@pytest.mark.unit
class TestMetricsListener:
    @pytest.mark.asyncio
    async def test_before_call_invokes_metrics(self) -> None:
        metrics = MagicMock()
        listener = MetricsListener(metrics)
        cb = MagicMock()
        cb.name = "cb1"

        async def func() -> None:
            return None

        await listener.before_call(cb, func, 1, kw=2)
        metrics.before_call.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_failure_and_success_after_call(self) -> None:
        metrics = MagicMock()
        listener = MetricsListener(metrics)
        cb = MagicMock()
        cb.name = "cb1"

        await listener.failure(cb, ValueError("x"))
        metrics.after_call.assert_called_with(name="cb1", result="failure")

        await listener.success(cb)
        metrics.after_call.assert_called_with(name="cb1", result="success")

    @pytest.mark.asyncio
    async def test_state_change_maps_states(self) -> None:
        metrics = MagicMock()
        listener = MetricsListener(metrics)
        cb = MagicMock()
        cb.name = "cb1"
        old = LibState.CLOSED
        new = LibState.OPEN

        await listener.state_change(cb, old, new)

        metrics.on_state_change.assert_called_once_with(
            name="cb1",
            old_state="closed",
            new_state="open",
        )


@pytest.mark.unit
class TestLoggingListener:
    @pytest.mark.asyncio
    async def test_before_call_logs_debug(self) -> None:
        log = MagicMock()
        log.bind.return_value = log
        listener = LoggingListener(log)
        cb = MagicMock()
        cb.name = "cb1"

        async def my_handler() -> None:
            return None

        await listener.before_call(cb, my_handler, 1, x=2)
        log.debug.assert_called_once()

    @pytest.mark.asyncio
    async def test_state_change_logs_info(self) -> None:
        log = MagicMock()
        log.bind.return_value = log
        listener = LoggingListener(log)
        cb = MagicMock()
        cb.name = "cb1"
        old = LibState.HALF_OPEN
        new = LibState.CLOSED

        await listener.state_change(cb, old, new)
        log.info.assert_called_once()
