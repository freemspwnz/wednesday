"""Тесты is_telegram_retryable."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError

from app.exceptions import TooManyRequests
from presentation.aiogram.retry_predicate import is_telegram_retryable

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
    ],
)
def test_is_telegram_retryable(exc: BaseException, expected: bool) -> None:
    assert is_telegram_retryable(exc) is expected


@pytest.mark.unit
def test_unwraps_cause_chain() -> None:
    outer = RuntimeError("wrapper")
    outer.__cause__ = _tmr()
    assert is_telegram_retryable(outer) is True
