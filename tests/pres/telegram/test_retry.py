"""Tests for is_telegram_retryable."""

from unittest.mock import MagicMock

import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from aiohttp import ClientError

from app.exceptions import TooManyRequests
from presentation.aiogram.predicate import is_telegram_retryable

_TELEGRAM_METHOD = MagicMock()


def _tmr() -> TooManyRequests:
    return TooManyRequests(retry_after=1, reset_at=0.0, limit="test")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (TelegramNetworkError(method=_TELEGRAM_METHOD, message="x"), True),
        (TelegramRetryAfter(method=_TELEGRAM_METHOD, message="x", retry_after=3), True),
        (TelegramServerError(method=_TELEGRAM_METHOD, message="x"), True),
        (_tmr(), True),
        (ValueError("x"), False),
        (TimeoutError(), False),
    ],
)
def test_is_telegram_retryable(exc: BaseException, expected: bool) -> None:
    assert is_telegram_retryable(exc) is expected


@pytest.mark.unit
def test_unwraps_cause_chain() -> None:
    outer = RuntimeError("wrapper")
    outer.__cause__ = _tmr()
    assert is_telegram_retryable(outer) is True


@pytest.mark.unit
def test_telegram_network_error_from_timeout_is_retryable() -> None:
    try:
        raise TelegramNetworkError(
            method=_TELEGRAM_METHOD,
            message="Request timeout error",
        ) from TimeoutError()
    except TelegramNetworkError as exc:
        assert is_telegram_retryable(exc) is True


@pytest.mark.unit
def test_telegram_server_error_from_timeout_is_retryable() -> None:
    try:
        raise TelegramServerError(
            method=_TELEGRAM_METHOD,
            message="Bad Gateway",
        ) from TimeoutError()
    except TelegramServerError as exc:
        assert is_telegram_retryable(exc) is True


@pytest.mark.unit
def test_telegram_network_error_from_aiohttp_client_error_is_retryable() -> None:
    try:
        raise TelegramNetworkError(
            method=_TELEGRAM_METHOD,
            message="ClientConnectorError",
        ) from ClientError()
    except TelegramNetworkError as exc:
        assert is_telegram_retryable(exc) is True


@pytest.mark.unit
def test_suppressed_retryable_context_is_not_retryable() -> None:
    try:
        try:
            raise TelegramNetworkError(method=_TELEGRAM_METHOD, message="x")
        except TelegramNetworkError:
            raise ValueError("outer") from None
    except ValueError as exc:
        assert is_telegram_retryable(exc) is False
