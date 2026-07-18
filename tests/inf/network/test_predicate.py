"""Tests for is_httpx_retryable."""

from http import HTTPStatus

import httpx2
import pytest

from app.exceptions import CircuitOpenError, TooManyRequests
from infra.network.httpx.predicate import is_httpx_retryable


def _status_error(status: int) -> httpx2.HTTPStatusError:
    request = httpx2.Request("GET", "https://example.com/x")
    response = httpx2.Response(status, request=request)
    return httpx2.HTTPStatusError("err", request=request, response=response)


@pytest.mark.unit
class TestIsHttpxRetryable:
    def test_timeout_is_retryable(self) -> None:
        assert is_httpx_retryable(httpx2.ReadTimeout("t")) is True

    def test_transport_is_retryable(self) -> None:
        assert is_httpx_retryable(httpx2.ConnectError("down")) is True

    @pytest.mark.parametrize(
        "status",
        [
            HTTPStatus.TOO_MANY_REQUESTS,
            HTTPStatus.INTERNAL_SERVER_ERROR,
            HTTPStatus.BAD_GATEWAY,
            HTTPStatus.SERVICE_UNAVAILABLE,
            HTTPStatus.GATEWAY_TIMEOUT,
            599,
        ],
    )
    def test_retryable_status_codes(self, status: int) -> None:
        assert is_httpx_retryable(_status_error(status)) is True

    @pytest.mark.parametrize(
        "status",
        [
            HTTPStatus.BAD_REQUEST,
            HTTPStatus.UNAUTHORIZED,
            HTTPStatus.FORBIDDEN,
            HTTPStatus.NOT_FOUND,
            HTTPStatus.UNPROCESSABLE_ENTITY,
        ],
    )
    def test_non_retryable_client_errors(self, status: int) -> None:
        assert is_httpx_retryable(_status_error(status)) is False

    def test_circuit_open_and_rate_limit_are_retryable(self) -> None:
        assert is_httpx_retryable(CircuitOpenError("open", retry_after=1.0)) is True
        assert is_httpx_retryable(TooManyRequests(retry_after=1, reset_at=0.0, limit="base")) is True

    def test_unknown_exception_is_not_retryable(self) -> None:
        assert is_httpx_retryable(ValueError("x")) is False
