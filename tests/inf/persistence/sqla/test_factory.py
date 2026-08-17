"""SQLAUoWFactory tests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from sqlalchemy import create_engine as create_sync_engine, text

import infra.persistence.sqlalchemy.factory as sqla_factory
from app.exceptions import DBUnavailableError
from infra.config.persistence.postgres import PostgresConfig
from infra.observe.prometheus.adapters.sqla import SQLAMetrics
from infra.persistence.sqlalchemy.factory import SQLAUoWFactory


@pytest.mark.unit
@pytest.mark.infra
def test_sqlauowfactory_passes_expected_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    sync_engine = Mock()
    engine = Mock()
    engine.sync_engine = sync_engine
    metrics = MagicMock()
    attach = MagicMock()

    def _fake_create_async_engine(**kwargs: object) -> Mock:
        captured.update(kwargs)
        return engine

    monkeypatch.setattr(sqla_factory, "create_async_engine", _fake_create_async_engine)
    monkeypatch.setattr(SQLAUoWFactory, "_attach_engine_metrics", attach)
    config = PostgresConfig(
        url="postgresql://user:pass@localhost:5432/test_db",
        pool_pre_ping=True,
        echo=False,
        pool_size=3,
        max_overflow=7,
    )
    logger = Mock()

    factory = SQLAUoWFactory(config=config, metrics=metrics, logger=logger)
    got = factory._engine

    assert got is engine
    assert captured["pool_pre_ping"] is True
    assert captured["pool_size"] == 3
    assert captured["max_overflow"] == 7
    assert str(captured["url"]).startswith("postgresql+asyncpg://")
    attach.assert_called_once_with(sync_engine, metrics)


@pytest.mark.unit
@pytest.mark.infra
def test_attach_engine_metrics_delegates_to_db_metrics(mock_logger: MagicMock) -> None:
    from prometheus_client import CollectorRegistry

    from infra.config.observe import MetricsConfig
    from infra.observe.prometheus import PrometheusCollector

    collector = PrometheusCollector(
        config=MetricsConfig(enabled=False, host="127.0.0.1", port=0),
        env="TEST",
        version="0.0.1",
        registry=CollectorRegistry(),
        logger=mock_logger,
    )
    metrics = SQLAMetrics(collector=collector)
    engine = create_sync_engine("sqlite:///:memory:")
    SQLAUoWFactory._attach_engine_metrics(engine, metrics)

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    out = collector.export().decode()
    assert "sqlalchemy_queries_total" in out
    engine.dispose()


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_aclose_logs_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _fake_timeout(_: float) -> AsyncIterator[None]:
        yield

    async def _timeout_dispose() -> None:
        raise TimeoutError

    engine = Mock()
    engine.dispose = AsyncMock(side_effect=_timeout_dispose)
    logger = Mock()
    logger.bind.return_value = logger
    config = PostgresConfig(url="postgresql://user:pass@localhost:5432/test_db")
    factory = SQLAUoWFactory(config=config, metrics=MagicMock(), logger=logger)
    factory.__dict__["_engine"] = engine

    monkeypatch.setattr(sqla_factory.asyncio, "timeout", _fake_timeout)

    await factory.aclose()

    logger.warning.assert_called_once()
    logger.info.assert_called_once()


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_aclose_logs_non_critical_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _fake_timeout(_: float) -> AsyncIterator[None]:
        yield

    engine = Mock()
    engine.dispose = AsyncMock(side_effect=RuntimeError("boom"))
    logger = Mock()
    logger.bind.return_value = logger
    config = PostgresConfig(url="postgresql://user:pass@localhost:5432/test_db")
    factory = SQLAUoWFactory(config=config, metrics=MagicMock(), logger=logger)
    factory.__dict__["_engine"] = engine

    monkeypatch.setattr(sqla_factory.asyncio, "timeout", _fake_timeout)

    await factory.aclose()

    logger.error.assert_called_once()
    logger.info.assert_called_once()


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_warmup_executes_select_1() -> None:
    conn = AsyncMock()
    connect_cm = AsyncMock()
    connect_cm.__aenter__.return_value = conn
    connect_cm.__aexit__.return_value = False
    engine = MagicMock()
    engine.connect.return_value = connect_cm
    logger = Mock()
    logger.bind.return_value = logger
    config = PostgresConfig(url="postgresql://user:pass@localhost:5432/test_db")
    factory = SQLAUoWFactory(config=config, metrics=MagicMock(), logger=logger)
    factory.__dict__["_engine"] = engine

    await factory.warmup()

    conn.execute.assert_awaited_once()
    statement = conn.execute.await_args.args[0]
    assert str(statement) == "SELECT 1"


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_warmup_maps_oserror_to_db_unavailable() -> None:
    engine = MagicMock()
    engine.connect.side_effect = OSError("refused")
    logger = Mock()
    logger.bind.return_value = logger
    config = PostgresConfig(url="postgresql://user:pass@localhost:5432/test_db")
    factory = SQLAUoWFactory(config=config, metrics=MagicMock(), logger=logger)
    factory.__dict__["_engine"] = engine

    with pytest.raises(DBUnavailableError, match="Database is not available") as exc_info:
        await factory.warmup()

    assert isinstance(exc_info.value.__cause__, OSError)
    logger.error.assert_called_once()
