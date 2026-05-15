from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock

import pytest

import infra.persistence.sqlalchemy.factory as sqla_factory
from infra.config.persistence.postgres import PostgresConfig


@pytest.mark.unit
@pytest.mark.infra
def test_create_engine_passes_expected_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    engine = Mock()

    def _fake_create_async_engine(**kwargs: object) -> Mock:
        captured.update(kwargs)
        return engine

    monkeypatch.setattr(sqla_factory, "create_async_engine", _fake_create_async_engine)
    config = PostgresConfig(
        url="postgresql://user:pass@localhost:5432/test_db",
        pool_pre_ping=True,
        echo=False,
        pool_size=3,
        max_overflow=7,
    )
    logger = Mock()

    got = sqla_factory.create_engine(config=config, logger=logger)

    assert got is engine
    assert captured["pool_pre_ping"] is True
    assert captured["pool_size"] == 3
    assert captured["max_overflow"] == 7
    assert str(captured["url"]).startswith("postgresql+asyncpg://")


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_close_engine_logs_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _fake_timeout(_: float) -> AsyncIterator[None]:
        yield

    async def _timeout_dispose() -> None:
        raise TimeoutError

    engine = Mock()
    engine.dispose = AsyncMock(side_effect=_timeout_dispose)
    logger = Mock()

    monkeypatch.setattr(sqla_factory.asyncio, "timeout", _fake_timeout)

    await sqla_factory.close_engine(engine=engine, logger=logger)

    logger.warning.assert_called_once()
    logger.info.assert_called_once()


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_close_engine_logs_non_critical_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _fake_timeout(_: float) -> AsyncIterator[None]:
        yield

    engine = Mock()
    engine.dispose = AsyncMock(side_effect=RuntimeError("boom"))
    logger = Mock()
    monkeypatch.setattr(sqla_factory.asyncio, "timeout", _fake_timeout)

    await sqla_factory.close_engine(engine=engine, logger=logger)

    logger.error.assert_called_once()
    logger.info.assert_called_once()
