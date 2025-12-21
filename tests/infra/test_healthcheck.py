from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from infra.healthcheck import app

HTTP_OK = 200
HTTP_SERVICE_UNAVAILABLE = 503


class _DummyPgConn:
    async def execute(self, query: str) -> None:
        return None


class _DummyPgAcquire:
    async def __aenter__(self) -> _DummyPgConn:
        return _DummyPgConn()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _DummyPgPool:
    def acquire(self) -> _DummyPgAcquire:
        return _DummyPgAcquire()


class _FailingPgAcquire:
    """Контекстный менеджер для acquire, который выбрасывает исключение при входе."""

    async def __aenter__(self) -> None:
        import asyncpg

        raise asyncpg.PostgresError("Connection refused")

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _FailingPgPool:
    """Postgres пул, который выбрасывает исключение при acquire, симулируя недоступность."""

    def acquire(self) -> _FailingPgAcquire:
        return _FailingPgAcquire()


class _DummyRedis:
    async def ping(self) -> bool:
        return True

    async def xinfo_stream(self, name: str) -> dict[str, Any]:
        # Для healthcheck нам не важны конкретные поля, достаточно успешного вызова.
        return {"length": 0}


class _FailingRedis:
    """Redis‑клиент, который выбрасывает исключение при ping/stream, симулируя недоступность."""

    async def ping(self) -> bool:
        from redis.exceptions import RedisError

        raise RedisError("Connection refused")

    async def xinfo_stream(self, name: str) -> dict[str, Any]:
        from redis.exceptions import RedisError

        raise RedisError("Connection refused")


@pytest.fixture()
def client() -> TestClient:
    """HTTP‑клиент для FastAPI‑приложения healthcheck."""
    return TestClient(app)


def test_health_all_dependencies_up(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Проверяем, что при доступных Redis/Postgres/очереди возвращается 200 и status=up."""
    from services import healthcheck

    # Патчим функции в модуле healthcheck, где они импортированы.
    # Также устанавливаем app.state, чтобы тесты использовали моки напрямую.
    healthcheck.app.state.redis = _DummyRedis()
    healthcheck.app.state.postgres_pool = _DummyPgPool()

    response = client.get("/health")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["status"] == "up"
    assert body["redis"]["status"] == "up"
    assert body["postgres"]["status"] == "up"
    assert body["queues"]["metrics_events"]["status"] == "up"


def test_health_redis_down_returns_503(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Если Redis недоступен, healthcheck должен вернуть 503 и status=down."""
    from services import healthcheck

    # Redis недоступен - устанавливаем клиент, который выбрасывает исключение.
    healthcheck.app.state.redis = _FailingRedis()
    # Postgres при этом доступен.
    healthcheck.app.state.postgres_pool = _DummyPgPool()

    response = client.get("/health")

    assert response.status_code == HTTP_SERVICE_UNAVAILABLE
    body = response.json()
    assert body["status"] == "down"
    assert body["redis"]["status"] == "down"


def test_health_postgres_down_returns_503(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Если Postgres недоступен, healthcheck должен вернуть 503 и status=down."""
    from services import healthcheck

    # Redis доступен.
    healthcheck.app.state.redis = _DummyRedis()
    # Postgres пул выбрасывает исключение при использовании (симулируя недоступность).
    healthcheck.app.state.postgres_pool = _FailingPgPool()

    response = client.get("/health")

    assert response.status_code == HTTP_SERVICE_UNAVAILABLE
    body = response.json()
    assert body["status"] == "down"
    assert body["postgres"]["status"] == "down"
