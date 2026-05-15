import pytest

from app.exceptions import (
    CircuitOpenError,
    SQLAAggregateMappingError,
    SQLADataIntegrityError,
    SQLARepositoryError,
    TooManyRequests,
    unwrap_exception,
)


@pytest.mark.unit
def test_unwrap_exception_returns_root_cause() -> None:
    root = ValueError("root")
    wrapped = RuntimeError("wrapped")
    wrapped.__cause__ = root

    assert unwrap_exception(wrapped) is root


@pytest.mark.unit
def test_too_many_requests_keeps_payload_fields() -> None:
    exc = TooManyRequests(
        retry_after=30,
        reset_at=123.45,
        remaining=0,
        limit="daily",
    )
    assert exc.retry_after == 30
    assert exc.reset_at == 123.45
    assert exc.remaining == 0
    assert exc.limit == "daily"


@pytest.mark.unit
def test_sqla_error_hierarchy_and_context() -> None:
    base = SQLARepositoryError("boom", operation="save", entity="user", entity_id=42)
    integrity = SQLADataIntegrityError("integrity", operation="save", entity="chat", entity_id="x")
    mapping = SQLAAggregateMappingError("mapping", operation="get_by_id", entity="chat")

    assert base.operation == "save"
    assert base.entity == "user"
    assert base.entity_id == 42
    assert isinstance(integrity, SQLARepositoryError)
    assert isinstance(mapping, SQLARepositoryError)


@pytest.mark.unit
def test_circuit_open_error_keeps_retry_after() -> None:
    exc = CircuitOpenError("open", retry_after=1.5)
    assert exc.retry_after == 1.5
