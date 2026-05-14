"""Тесты listeners и ``CircuitState`` для asyncbreaker-среза."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from infra.resilience.asyncbreaker.listeners.logging import LoggingListener
from infra.resilience.asyncbreaker.listeners.metrics import MetricsListener
from infra.resilience.asyncbreaker.state import CircuitState


def _state_mock(name: str) -> MagicMock:
    m = MagicMock()
    m.state.name = name
    return m


@pytest.mark.unit
class TestCircuitState:
    def test_from_external_closed(self) -> None:
        ext = _state_mock("CLOSED")
        assert CircuitState.from_external(ext) is CircuitState.CLOSED

    def test_from_external_open(self) -> None:
        ext = _state_mock("OPEN")
        assert CircuitState.from_external(ext) is CircuitState.OPEN

    def test_from_external_unknown_maps_to_unknown(self) -> None:
        ext = _state_mock("NOT_A_REAL_STATE")
        assert CircuitState.from_external(ext) is CircuitState.UNKNOWN

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
        old = _state_mock("CLOSED")
        new = _state_mock("OPEN")

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
        listener = LoggingListener(log)
        cb = MagicMock()
        cb.name = "cb1"
        old = _state_mock("HALF_OPEN")
        new = _state_mock("CLOSED")

        await listener.state_change(cb, old, new)
        log.info.assert_called_once()
