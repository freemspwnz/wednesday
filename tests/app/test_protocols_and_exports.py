import pytest

import app.dto as dto_module
import app.exceptions as exc_module
import app.protocols as proto_module
from app.protocols.observe import (
    ICacheMetrics,
    ICBMetrics,
    IMetricsCollector,
    IMetricsRegistry,
    IRetryMetrics,
    IRLMetrics,
    ISQLAMetrics,
    Logger,
)
from app.protocols.persistence import ICacheClient, ICacheRepo, ICacheRepoRegistry, IUoW, IUoWFactory
from app.protocols.resilience import ICircuitBreaker, IRateLimiter, IRetryPolicy


@pytest.mark.unit
def test_public_exports_are_available() -> None:
    assert hasattr(dto_module, "UserContext")
    assert hasattr(dto_module, "ChatContext")
    assert hasattr(exc_module, "SQLARepositoryError")
    assert hasattr(exc_module, "TooManyRequests")
    assert hasattr(proto_module, "IUoW")
    assert hasattr(proto_module, "Logger")


@pytest.mark.unit
def test_protocol_symbols_import_correctly() -> None:
    # runtime smoke for protocol modules and __all__ wiring
    symbols = [
        Logger,
        IMetricsCollector,
        IRetryMetrics,
        ICBMetrics,
        ICacheMetrics,
        ISQLAMetrics,
        IRLMetrics,
        IMetricsRegistry,
        ICacheClient,
        ICacheRepo,
        ICacheRepoRegistry,
        IUoW,
        IUoWFactory,
        ICircuitBreaker,
        IRateLimiter,
        IRetryPolicy,
    ]
    assert all(symbol is not None for symbol in symbols)
