from __future__ import annotations

import asyncio
from typing import Any

import pytest
from loguru import logger

from infra.clients.gigachat_text import GigaChatTextClient
from shared.config import GigaChatConfig, HttpTimeoutConfig
from tests.conftest import _InMemoryModelsRepo


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
    timeout = HttpTimeoutConfig(total=60, connect=10, sock_read=30)
    config = GigaChatConfig(
        auth_url="https://example.test/auth",
        api_url="https://example.test/api",
        models_url="https://example.test/models",
        authorization_key="dummy",
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        verify_ssl=False,
        prompt_timeout=timeout,
        models_timeout=timeout,
        token_timeout=timeout,
    )

    models_repo = _InMemoryModelsRepo()
    async with GigaChatTextClient(config=config, models_repo=models_repo) as client:
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


@pytest.mark.asyncio
async def test_gigachat_text_client_authorization_key_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Проверяем, что при логировании authorization_key используется только preview,
    а полный ключ в лог не попадает.
    """
    full_key = "A" * 40

    timeout = HttpTimeoutConfig(total=60, connect=10, sock_read=30)
    config = GigaChatConfig(
        auth_url="https://example.test/auth",
        api_url="https://example.test/api",
        models_url="https://example.test/models",
        authorization_key=full_key,
        scope="GIGACHAT_API_PERS",
        model="GigaChat",
        verify_ssl=False,
        prompt_timeout=timeout,
        models_timeout=timeout,
        token_timeout=timeout,
    )

    models_repo = _InMemoryModelsRepo()
    async with GigaChatTextClient(config=config, models_repo=models_repo) as client:
        # Подменяем session, чтобы не было реальных HTTP‑запросов.
        dummy_session = _DummySession()
        monkeypatch.setattr(client, "_session", dummy_session, raising=True)

        # Захватываем логи в буфер.
        from io import StringIO

        buffer = StringIO()
        sink_id = logger.add(buffer, level="DEBUG")

        try:
            # Принудительно сбрасываем кэш токена и вызываем _get_access_token.
            client._access_token = None
            client._token_expiry_time = None

            await client._get_access_token()
        finally:
            logger.remove(sink_id)

        log_text = buffer.getvalue()

        # В логах должен быть только preview (первые 10 символов + '...'),
        # но не полный ключ.
        preview = full_key[:10]
        assert preview in log_text
        assert full_key not in log_text
