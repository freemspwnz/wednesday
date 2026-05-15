"""Тесты обёртки ``Asyncbreaker`` над asyncbreaker."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from asyncbreaker import StorageError
from asyncbreaker.state import CircuitBreakerError
from asyncbreaker.timeutil import naive_utc_now

from app.exceptions import AppError, CircuitOpenError, CircuitStorageError, UnexpectedCircuitError
from infra.resilience.asyncbreaker.breaker import Asyncbreaker


class _DomainAppError(AppError):
    """Тестовая доменная ошибка для проверки проброса ``AppError``."""


@pytest.fixture
def mock_logger() -> MagicMock:
    log = MagicMock()
    log.bind.return_value = log
    return log


@pytest.fixture
def mock_breaker() -> MagicMock:
    b = MagicMock()
    b.name = "unit-cb"
    return b


@pytest.fixture
def async_breaker(mock_breaker: MagicMock, mock_logger: MagicMock) -> Asyncbreaker:
    return Asyncbreaker(breaker=mock_breaker, logger=mock_logger)


@pytest.mark.unit
class TestAsyncBreakerCall:
    @pytest.mark.asyncio
    async def test_success_returns_result(
        self,
        async_breaker: Asyncbreaker,
        mock_breaker: MagicMock,
    ) -> None:
        async def work(x: int) -> int:
            return x * 2

        mock_breaker.call = AsyncMock(return_value=84)
        out = await async_breaker.call(work, 21)
        assert out == 84
        mock_breaker.call.assert_awaited_once_with(work, 21)

    @pytest.mark.asyncio
    async def test_decorator_delegates_to_call(
        self,
        async_breaker: Asyncbreaker,
        mock_breaker: MagicMock,
    ) -> None:
        async def work() -> str:
            return "ok"

        mock_breaker.call = AsyncMock(return_value="wrapped")
        decorated = async_breaker(work)
        assert await decorated() == "wrapped"

    @pytest.mark.asyncio
    async def test_circuit_breaker_error_maps_to_circuit_open(
        self,
        async_breaker: Asyncbreaker,
        mock_breaker: MagicMock,
    ) -> None:
        async def work() -> None:
            return None

        reopen = naive_utc_now() + timedelta(seconds=100)
        mock_breaker.call = AsyncMock(
            side_effect=CircuitBreakerError("open", reopen_time=reopen),
        )

        with pytest.raises(CircuitOpenError) as ei:
            await async_breaker.call(work)

        assert "unit-cb" in str(ei.value)
        assert 90.0 <= ei.value.retry_after <= 100.5
        assert isinstance(ei.value.__cause__, CircuitBreakerError)

    @pytest.mark.asyncio
    async def test_circuit_breaker_error_without_reopen_zero_retry_after(
        self,
        async_breaker: Asyncbreaker,
        mock_breaker: MagicMock,
    ) -> None:
        async def work() -> None:
            return None

        mock_breaker.call = AsyncMock(
            side_effect=CircuitBreakerError("open", reopen_time=None),
        )

        with pytest.raises(CircuitOpenError) as ei:
            await async_breaker.call(work)

        assert ei.value.retry_after == 0.0

    @pytest.mark.asyncio
    async def test_storage_error_maps_to_circuit_storage_error(
        self,
        async_breaker: Asyncbreaker,
        mock_breaker: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        async def work() -> None:
            return None

        mock_breaker.call = AsyncMock(side_effect=StorageError("redis down"))

        with pytest.raises(CircuitStorageError) as ei:
            await async_breaker.call(work)

        assert "unavailable" in str(ei.value).lower()
        assert isinstance(ei.value.__cause__, StorageError)
        mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_app_error_passes_through(
        self,
        async_breaker: Asyncbreaker,
        mock_breaker: MagicMock,
    ) -> None:
        async def work() -> None:
            return None

        err = _DomainAppError("domain boom")
        mock_breaker.call = AsyncMock(side_effect=err)

        with pytest.raises(_DomainAppError) as ei:
            await async_breaker.call(work)

        assert ei.value is err

    @pytest.mark.asyncio
    async def test_generic_exception_maps_to_unexpected_circuit(
        self,
        async_breaker: Asyncbreaker,
        mock_breaker: MagicMock,
        mock_logger: MagicMock,
    ) -> None:
        async def work() -> None:
            return None

        mock_breaker.call = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(UnexpectedCircuitError) as ei:
            await async_breaker.call(work)

        assert isinstance(ei.value.__cause__, RuntimeError)
        mock_logger.exception.assert_called_once()


@pytest.mark.unit
class TestAsyncBreakerStateMutators:
    @pytest.mark.asyncio
    async def test_open_success(
        self,
        async_breaker: Asyncbreaker,
        mock_breaker: MagicMock,
    ) -> None:
        mock_breaker.open = AsyncMock(return_value=None)
        await async_breaker.open()
        mock_breaker.open.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_open_storage_error(
        self,
        async_breaker: Asyncbreaker,
        mock_breaker: MagicMock,
    ) -> None:
        mock_breaker.open = AsyncMock(side_effect=StorageError("x"))
        with pytest.raises(CircuitStorageError):
            await async_breaker.open()

    @pytest.mark.asyncio
    async def test_half_open_storage_error(
        self,
        async_breaker: Asyncbreaker,
        mock_breaker: MagicMock,
    ) -> None:
        mock_breaker.half_open = AsyncMock(side_effect=StorageError("x"))
        with pytest.raises(CircuitStorageError):
            await async_breaker.half_open()

    @pytest.mark.asyncio
    async def test_close_storage_error(
        self,
        async_breaker: Asyncbreaker,
        mock_breaker: MagicMock,
    ) -> None:
        mock_breaker.close = AsyncMock(side_effect=StorageError("x"))
        with pytest.raises(CircuitStorageError):
            await async_breaker.close()
