"""
Тесты для модуля utils.retry.

Проверяет:
- Декораторы retry с различными исключениями
- Логирование retry
- Корректное выбрасывание ошибки после всех попыток
- Экспоненциальный backoff
- Исключение определённых HTTP-статусов из retry
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from utils.retry import retry_critical, retry_optional, retry_standard, retry_with_logging

pytestmark = [pytest.mark.unit, pytest.mark.slow]

# Константы для тестов
MAX_ATTEMPTS_2 = 2
MAX_ATTEMPTS_3 = 3
MAX_ATTEMPTS_4 = 4
MAX_ATTEMPTS_5 = 5


@pytest.mark.asyncio
async def test_retry_success() -> None:
    """Тест успешного выполнения без retry."""
    call_count = 0

    @retry_standard(service_name="test", method_name="test_success")
    async def successful_function() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0)  # Используем async для соответствия декоратору
        return "success"

    result = await successful_function()
    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_on_client_connector_error() -> None:
    """Тест retry при ClientConnectorError."""
    call_count = 0

    @retry_standard(service_name="test", method_name="test_connector_error", max_attempts=MAX_ATTEMPTS_3)
    async def failing_function() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0)
        if call_count < MAX_ATTEMPTS_3:
            raise aiohttp.ClientConnectorError(
                connection_key=MagicMock(),
                os_error=OSError("Connection refused"),
            )
        return "success"

    result = await failing_function()
    assert result == "success"
    assert call_count == MAX_ATTEMPTS_3


@pytest.mark.asyncio
async def test_retry_on_timeout_error() -> None:
    """Тест retry при TimeoutError."""
    call_count = 0

    @retry_standard(service_name="test", method_name="test_timeout", max_attempts=2)
    async def timeout_function() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise TimeoutError("Request timeout")
        return "success"

    result = await timeout_function()
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausted_raises_exception() -> None:
    """Тест выбрасывания исключения после исчерпания всех попыток."""
    call_count = 0

    @retry_standard(service_name="test", method_name="test_exhausted", max_attempts=3)
    async def always_failing_function() -> str:
        nonlocal call_count
        call_count += 1
        raise aiohttp.ClientConnectorError(
            connection_key=MagicMock(),
            os_error=OSError("Connection refused"),
        )

    with pytest.raises(aiohttp.ClientConnectorError):
        await always_failing_function()

    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_no_retry_on_401() -> None:
    """Тест отсутствия retry для HTTP 401 (Unauthorized)."""
    call_count = 0

    @retry_standard(service_name="test", method_name="test_401", max_attempts=3)
    async def unauthorized_function() -> str:
        nonlocal call_count
        call_count += 1
        error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=401,
            message="Unauthorized",
        )
        raise error

    with pytest.raises(aiohttp.ClientResponseError):
        await unauthorized_function()

    # Не должно быть retry для 401
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_no_retry_on_403() -> None:
    """Тест отсутствия retry для HTTP 403 (Forbidden)."""
    call_count = 0

    @retry_standard(service_name="test", method_name="test_403", max_attempts=3)
    async def forbidden_function() -> str:
        nonlocal call_count
        call_count += 1
        error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=403,
            message="Forbidden",
        )
        raise error

    with pytest.raises(aiohttp.ClientResponseError):
        await forbidden_function()

    # Не должно быть retry для 403
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_no_retry_on_400() -> None:
    """Тест отсутствия retry для HTTP 400 (Bad Request)."""
    call_count = 0

    @retry_standard(service_name="test", method_name="test_400", max_attempts=3)
    async def bad_request_function() -> str:
        nonlocal call_count
        call_count += 1
        error = aiohttp.ClientResponseError(
            request_info=MagicMock(),
            history=(),
            status=400,
            message="Bad Request",
        )
        raise error

    with pytest.raises(aiohttp.ClientResponseError):
        await bad_request_function()

    # Не должно быть retry для 400
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_critical_max_attempts() -> None:
    """Тест retry_critical с максимальным количеством попыток."""
    call_count = 0

    @retry_critical(service_name="test", method_name="test_critical", max_attempts=5)
    async def critical_function() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 5:
            raise aiohttp.ServerTimeoutError()
        return "success"

    result = await critical_function()
    assert result == "success"
    assert call_count == 5


@pytest.mark.asyncio
async def test_retry_optional_max_attempts() -> None:
    """Тест retry_optional с минимальным количеством попыток."""
    call_count = 0

    @retry_optional(service_name="test", method_name="test_optional", max_attempts=2)
    async def optional_function() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise aiohttp.ClientError()
        return "success"

    result = await optional_function()
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_with_logging() -> None:
    """Тест универсального декоратора retry_with_logging."""
    call_count = 0

    @retry_with_logging(service_name="test", method_name="test_logging", max_attempts=3)
    async def logging_function() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise aiohttp.ClientConnectorError(
                connection_key=MagicMock(),
                os_error=OSError("Connection refused"),
            )
        return "success"

    result = await logging_function()
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_logging_called() -> None:
    """Тест логирования retry через log_event."""
    call_count = 0

    with patch("utils.retry.log_event") as mock_log_event:

        @retry_standard(service_name="test", method_name="test_logging_called", max_attempts=3)
        async def logging_function() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise aiohttp.ClientConnectorError(
                    connection_key=MagicMock(),
                    os_error=OSError("Connection refused"),
                )
            return "success"

        result = await logging_function()
        assert result == "success"
        assert call_count == 3

        # Проверяем, что log_event вызывался для retry
        assert mock_log_event.called
        # Проверяем, что были вызовы с event="test_retry"
        # log_event вызывается с event как первый позиционный аргумент
        retry_calls = [
            call_obj
            for call_obj in mock_log_event.call_args_list
            if (call_obj.args and len(call_obj.args) > 0 and call_obj.args[0] == "test_retry")
            or (call_obj.kwargs and call_obj.kwargs.get("event") == "test_retry")
        ]
        assert len(retry_calls) >= 2  # Должно быть минимум 2 retry


@pytest.mark.asyncio
async def test_retry_metrics_called() -> None:
    """Тест обновления метрик Prometheus при retry."""
    call_count = 0

    with (
        patch("utils.prometheus_metrics.HTTP_RETRIES_TOTAL", new_callable=MagicMock) as mock_retries_total,
        patch("utils.prometheus_metrics.HTTP_RETRY_WAIT_SECONDS", new_callable=MagicMock) as mock_retry_wait,
    ):

        @retry_standard(service_name="test", method_name="test_metrics", max_attempts=3)
        async def metrics_function() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise aiohttp.ClientConnectorError(
                    connection_key=MagicMock(),
                    os_error=OSError("Connection refused"),
                )
            return "success"

        result = await metrics_function()
        assert result == "success"
        assert call_count == 3

        # Метрики должны обновляться при retry
        # Проверяем, что labels вызывался (метрики обновляются через labels().inc() и labels().observe())
        assert mock_retries_total.labels.called or mock_retry_wait.labels.called


@pytest.mark.asyncio
async def test_retry_exponential_backoff() -> None:
    """Тест экспоненциального backoff (проверка задержек)."""
    call_times: list[float] = []

    @retry_standard(
        service_name="test",
        method_name="test_backoff",
        max_attempts=4,
    )
    async def backoff_function() -> str:
        import time

        call_times.append(time.time())
        if len(call_times) < 4:
            raise aiohttp.ClientConnectorError(
                connection_key=MagicMock(),
                os_error=OSError("Connection refused"),
            )
        return "success"

    # Мокируем sleep, чтобы ускорить тест
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await backoff_function()
        assert result == "success"
        assert len(call_times) == 4

        # Проверяем, что sleep вызывался (экспоненциальный backoff)
        assert mock_sleep.called
        # Проверяем, что задержки увеличиваются
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        if len(sleep_calls) >= 2:
            # Второй sleep должен быть больше первого (экспоненциальный рост)
            assert sleep_calls[1] >= sleep_calls[0]


@pytest.mark.asyncio
async def test_retry_non_retryable_exception() -> None:
    """Тест отсутствия retry для не-retryable исключений."""
    call_count = 0

    @retry_standard(service_name="test", method_name="test_non_retryable", max_attempts=3)
    async def non_retryable_function() -> str:
        nonlocal call_count
        call_count += 1
        raise ValueError("This should not be retried")

    with pytest.raises(ValueError):
        await non_retryable_function()

    # Не должно быть retry для ValueError
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_500_status_retried() -> None:
    """Тест retry для HTTP 500 (Internal Server Error)."""
    call_count = 0

    @retry_standard(service_name="test", method_name="test_500", max_attempts=3)
    async def server_error_function() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            error = aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=500,
                message="Internal Server Error",
            )
            raise error
        return "success"

    result = await server_error_function()
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_final_error_logged() -> None:
    """Тест логирования финальной ошибки после всех попыток."""
    call_count = 0

    with patch("utils.retry.log_event") as mock_log_event:

        @retry_standard(service_name="test", method_name="test_final_error", max_attempts=3)
        async def always_failing_function() -> str:
            nonlocal call_count
            call_count += 1
            raise aiohttp.ClientConnectorError(
                connection_key=MagicMock(),
                os_error=OSError("Connection refused"),
            )

        with pytest.raises(aiohttp.ClientConnectorError):
            await always_failing_function()

        assert call_count == 3

        # Проверяем, что была залогирована финальная ошибка
        failed_calls = [
            call_obj
            for call_obj in mock_log_event.call_args_list
            if (call_obj.args and len(call_obj.args) > 0 and call_obj.args[0] == "test_retry_failed")
            or (call_obj.kwargs and call_obj.kwargs.get("event") == "test_retry_failed")
        ]
        assert len(failed_calls) >= 1
