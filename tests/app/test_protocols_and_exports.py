import pytest

import app.dto as dto_module
import app.exceptions as exc_module
import app.protocols as proto_module
from app.protocols.observe import (
    CacheMetrics,
    CBMetrics,
    DBMetrics,
    Logger,
    MetricsCollector,
    MetricsRegistry,
    RetryMetrics,
    RLMetrics,
)
from app.protocols.persistence import CacheClient, CacheRepo, CacheRepoRegistry, UoW, UoWFactory
from app.protocols.resilience import CircuitBreaker, IRateLimiter, Retrier


@pytest.mark.unit
def test_public_exports_are_available() -> None:
    assert hasattr(dto_module, "UserContext")
    assert hasattr(dto_module, "ChatContext")
    assert hasattr(exc_module, "SQLARepositoryError")
    assert hasattr(exc_module, "TooManyRequests")
    assert hasattr(exc_module, "MaxAttemptsExhaustedError")
    assert hasattr(proto_module, "UoW")
    assert hasattr(proto_module, "Logger")


@pytest.mark.unit
def test_protocol_symbols_import_correctly() -> None:
    # runtime smoke for protocol modules and __all__ wiring
    symbols = [
        Logger,
        MetricsCollector,
        RetryMetrics,
        CBMetrics,
        CacheMetrics,
        DBMetrics,
        RLMetrics,
        MetricsRegistry,
        CacheClient,
        CacheRepo,
        CacheRepoRegistry,
        UoW,
        UoWFactory,
        CircuitBreaker,
        IRateLimiter,
        Retrier,
    ]
    assert all(symbol is not None for symbol in symbols)
