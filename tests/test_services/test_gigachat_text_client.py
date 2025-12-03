from __future__ import annotations

import asyncio
from typing import Any

import pytest

from services.clients.gigachat_text import GigaChatTextClient


class _DummyResponse:
    """Заглушка для aiohttp.ClientResponse, совместимая с retry-механикой."""

    def __init__(self) -> None:
        self.status = 200
        self.headers: dict[str, str] = {}

    async def json(self) -> dict[str, Any]:
        return {"access_token": "dummy-token", "expires_in": 1800}

    async def text(self) -> str:
        return ""

    async def read(self) -> bytes:
        return b""

    async def __aenter__(self) -> _DummyResponse:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _DummySession:
    """Заглушка для aiohttp.ClientSession, совместимая с retry-механикой."""

    def __init__(self) -> None:
        self.post_calls: int = 0
        self.get_calls: int = 0

    async def post(self, *args: Any, **kwargs: Any) -> _DummyResponse:
        """Асинхронный метод post для совместимости с retry."""
        self.post_calls += 1
        return _DummyResponse()

    async def get(self, *args: Any, **kwargs: Any) -> _DummyResponse:
        """Асинхронный метод get для совместимости с retry."""
        self.get_calls += 1
        return _DummyResponse()

    async def close(self) -> None:
        return None

    @property
    def calls(self) -> int:
        """Общее количество вызовов post и get для обратной совместимости."""
        return self.post_calls + self.get_calls


@pytest.mark.asyncio
async def test_gigachat_text_client_concurrent_token_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Проверяем, что при параллельных запросах токена фактически выполняется
    только один HTTP‑запрос и не возникает гонок.
    """
    client = GigaChatTextClient(
        auth_url="https://example.test/auth",
        api_url="https://example.test/api",
        authorization_key="dummy",
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        verify_ssl=False,
    )

    # Подменяем внутренний session на заглушку, чтобы не ходить в сеть.
    dummy_session = _DummySession()
    monkeypatch.setattr(client, "_session", dummy_session, raising=True)

    # Сбрасываем кэш токена явно.
    client._access_token = None
    client._token_expiry_time = None

    async def _worker() -> str | None:
        return await client._get_access_token()

    # Запускаем несколько конкурентных запросов токена.
    results = await asyncio.gather(*[_worker() for _ in range(10)])

    # Все корутины получили токен.
    assert all(r == "dummy-token" for r in results), f"Не все результаты равны 'dummy-token': {results}"
    # HTTP‑вызов был выполнен только один раз (благодаря lock в _get_access_token).
    assert dummy_session.post_calls == 1, f"Ожидался 1 вызов post, получено: {dummy_session.post_calls}"

    await client.aclose()
