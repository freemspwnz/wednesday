import pytest

from app.exceptions import (
    AggregateMappingError,
    AppError,
    CacheError,
    CacheTimeoutError,
    CacheUnavailableError,
    CircuitOpenError,
    DataIntegrityError,
    LoggingError,
    LogMessageFormatError,
    MetricsError,
    MetricsExportError,
    MetricsHttpExporterError,
    RepositoryError,
    TooManyRequests,
    UnknownProviderError,
    unwrap_exception,
)


@pytest.mark.unit
def test_unknown_provider_error_keeps_vendor() -> None:
    exc = UnknownProviderError("yandex")
    assert exc.vendor == "yandex"
    assert "yandex" in str(exc)
    assert isinstance(exc, AppError)


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
def test_db_error_hierarchy_and_context() -> None:
    base = RepositoryError("boom", operation="save", entity="user", entity_id=42)
    integrity = DataIntegrityError("integrity", operation="save", entity="chat", entity_id="x")
    mapping = AggregateMappingError("mapping", operation="get_by_id", entity="chat")

    assert base.operation == "save"
    assert base.entity == "user"
    assert base.entity_id == 42
    assert isinstance(integrity, RepositoryError)
    assert isinstance(mapping, RepositoryError)


@pytest.mark.unit
def test_circuit_open_error_keeps_retry_after() -> None:
    exc = CircuitOpenError("open", retry_after=1.5)
    assert exc.retry_after == 1.5


@pytest.mark.unit
def test_cache_error_hierarchy_and_operation() -> None:
    timeout = CacheTimeoutError("timed out", operation="get")
    unavailable = CacheUnavailableError("down", operation="set")

    assert isinstance(timeout, CacheError)
    assert isinstance(unavailable, CacheError)
    assert timeout.operation == "get"
    assert unavailable.operation == "set"


@pytest.mark.unit
def test_metrics_error_hierarchy() -> None:
    export_error = MetricsExportError("export failed")
    http_error = MetricsHttpExporterError("bind failed")

    assert isinstance(export_error, MetricsError)
    assert isinstance(http_error, MetricsError)


@pytest.mark.unit
def test_logging_error_hierarchy() -> None:
    err = LogMessageFormatError("msg {x}", (1,))

    assert isinstance(err, LoggingError)
    assert err.template == "msg {x}"
    assert err.log_args == (1,)
