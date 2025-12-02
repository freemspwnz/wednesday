from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from services.healthcheck import app

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


class _DummyRedis:
    async def ping(self) -> bool:
        return True

    async def xinfo_stream(self, name: str) -> dict[str, Any]:
        # Для healthcheck нам не важны конкретные поля, достаточно успешного вызова.
        return {"length": 0}


@pytest.fixture()
def client() -> TestClient:
    """HTTP‑клиент для FastAPI‑приложения healthcheck."""
    return TestClient(app)


def test_health_all_dependencies_up(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Проверяем, что при доступных Redis/Postgres/очереди возвращается 200 и status=up."""
    from services import healthcheck

    # Redis доступен, используем реальный (заглушечный) клиент.
    monkeypatch.setattr(healthcheck, "redis_available", lambda: True)
    monkeypatch.setattr(healthcheck, "get_redis", _DummyRedis)
    # Postgres пул успешно возвращается и выполняет SELECT 1.
    monkeypatch.setattr(healthcheck, "get_postgres_pool", _DummyPgPool)

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

    # Redis недоступен (используется in‑memory fallback).
    monkeypatch.setattr(healthcheck, "redis_available", lambda: False)
    # Postgres при этом доступен.
    monkeypatch.setattr(healthcheck, "get_postgres_pool", _DummyPgPool)

    response = client.get("/health")

    assert response.status_code == HTTP_SERVICE_UNAVAILABLE
    body = response.json()
    assert body["status"] == "down"
    assert body["redis"]["status"] == "down"


def test_health_postgres_down_returns_503(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    """Если Postgres не инициализирован, healthcheck должен вернуть 503 и status=down."""
    from services import healthcheck

    # Redis доступен, но Postgres пул не инициализирован.
    monkeypatch.setattr(healthcheck, "redis_available", lambda: True)
    monkeypatch.setattr(healthcheck, "get_redis", _DummyRedis)

    class _RaisesRuntimeError:
        def __call__(self) -> None:
            raise RuntimeError("Postgres pool not initialized")

    monkeypatch.setattr(healthcheck, "get_postgres_pool", _RaisesRuntimeError())

    response = client.get("/health")

    assert response.status_code == HTTP_SERVICE_UNAVAILABLE
    body = response.json()
    assert body["status"] == "down"
    assert body["postgres"]["status"] == "down"
