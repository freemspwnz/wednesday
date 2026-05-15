"""Тесты предиката is_retryable."""

from __future__ import annotations

import pytest

from app.exceptions import CircuitOpenError, TooManyRequests
from infra.resilience.tenacity.predicate import is_retryable


def _too_many_requests() -> TooManyRequests:
    return TooManyRequests(
        retry_after=1,
        reset_at=0.0,
        limit="test",
    )


@pytest.mark.unit
class TestIsRetryable:
    def test_circuit_open(self) -> None:
        assert is_retryable(CircuitOpenError("open", 1.0)) is True

    def test_too_many_requests(self) -> None:
        assert is_retryable(_too_many_requests()) is True

    def test_other_exception_false(self) -> None:
        assert is_retryable(ValueError("x")) is False

    def test_unwraps_cause_chain(self) -> None:
        inner = _too_many_requests()
        outer = RuntimeError("wrapper")
        outer.__cause__ = inner
        assert is_retryable(outer) is True
