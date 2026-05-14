"""Тесты backoff и get_retry_after."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from tenacity import RetryCallState
from tenacity.wait import wait_fixed

from infra.resilience.tenacity.backoff import (
    DEFAULT_RETRY_AFTER_SECONDS,
    MAX_DELAY_SECONDS,
    NO_RETRY_AFTER_SECONDS,
    get_retry_after,
    wait_priority,
)


@pytest.mark.unit
class TestGetRetryAfter:
    def test_retry_after_attribute_int(self) -> None:
        exc = _RetryAfterProbe(retry_after=12)
        assert get_retry_after(exc) == 12.0

    def test_retry_after_attribute_invalid_falls_back_to_default(self) -> None:
        exc = _RetryAfterProbe(retry_after="not-a-float")
        assert get_retry_after(exc) == DEFAULT_RETRY_AFTER_SECONDS

    def test_response_retry_after_numeric_header(self) -> None:
        exc = _RetryAfterProbe(
            retry_after=None,
            response=SimpleNamespace(headers={"Retry-After": "7"}),
        )
        assert get_retry_after(exc) == 7.0

    def test_response_retry_after_http_date(self) -> None:
        future = datetime.now(UTC) + timedelta(seconds=30)
        header = format_datetime(future)
        exc = _RetryAfterProbe(
            retry_after=None,
            response=SimpleNamespace(headers={"Retry-After": header}),
        )
        got = get_retry_after(exc)
        assert 25.0 <= got <= 35.0

    def test_response_retry_after_invalid_header_uses_default(self) -> None:
        exc = _RetryAfterProbe(
            retry_after=None,
            response=SimpleNamespace(headers={"Retry-After": "not-a-number-nor-date"}),
        )
        assert get_retry_after(exc) == DEFAULT_RETRY_AFTER_SECONDS

    def test_no_hints_returns_sentinel(self) -> None:
        assert get_retry_after(ValueError("plain")) == NO_RETRY_AFTER_SECONDS


@pytest.mark.unit
class TestWaitPriority:
    def test_uses_fallback_when_primary_exceeds_max(self) -> None:
        primary = wait_fixed(MAX_DELAY_SECONDS + 1.0)
        fallback = wait_fixed(2.5)
        wp = wait_priority(primary, fallback)
        state = MagicMock(spec=RetryCallState)
        assert wp(retry_state=state) == 2.5

    def test_uses_primary_when_within_max(self) -> None:
        primary = wait_fixed(100.0)
        fallback = wait_fixed(2.5)
        wp = wait_priority(primary, fallback)
        state = MagicMock(spec=RetryCallState)
        assert wp(retry_state=state) == 100.0


class _RetryAfterProbe(Exception):
    def __init__(
        self,
        *,
        retry_after: object | None = None,
        response: object | None = None,
    ) -> None:
        self.retry_after = retry_after
        self.response = response
