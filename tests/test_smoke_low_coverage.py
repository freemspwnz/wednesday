from __future__ import annotations

import signal
from typing import Any
from unittest.mock import MagicMock

import pytest

from bot.handlers import CommandHandlers
from services import prompt_cache as prompt_cache_module, rate_limiter as rate_limiter_module
from services.clients import factory as clients_factory
from utils.redis_client import _InMemoryRedis

pytestmark = [pytest.mark.unit]


def test_create_image_client_uses_container(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_client = MagicMock()
    dummy_container = MagicMock()

    monkeypatch.setattr(clients_factory, "KandinskyClient", lambda: dummy_client)
    monkeypatch.setattr(
        clients_factory,
        "get_image_client_container",
        lambda: dummy_container,
    )

    clients_factory.create_image_client()

    dummy_container.set_initial_client.assert_called_once_with(dummy_client)


def test_create_text_client_uses_container(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_container = MagicMock()

    class _DummyGigaChat:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.args = args
            self.kwargs = kwargs

    monkeypatch.setattr(clients_factory, "GigaChatTextClient", _DummyGigaChat)
    monkeypatch.setattr(
        clients_factory,
        "get_text_client_container",
        lambda: dummy_container,
    )
    # Минимизируем зависимость от реальных env/config
    monkeypatch.setenv("TEXT_MODEL_BACKEND", "gigachat")

    clients_factory.create_text_client()

    dummy_container.set_initial_client.assert_called_once()
    assert isinstance(dummy_container.set_initial_client.call_args.args[0], _DummyGigaChat)


@pytest.mark.asyncio
async def test_prompt_cache_inmemory_roundtrip() -> None:
    backend = _InMemoryRedis()
    cache = prompt_cache_module.PromptCache(redis_client=backend, prefix="smoke:", default_ttl=1)

    await cache.set("k", {"v": 1})
    assert await cache.exists("k") is True
    loaded = await cache.get("k")
    assert isinstance(loaded, dict)
    assert loaded["v"] == 1

    keys = await cache.keys("*")
    assert "k" in keys

    await cache.delete("k")
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_rate_limiter_and_circuit_breaker_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = _InMemoryRedis()
    rate = rate_limiter_module.RateLimiter(redis_client=backend, limit=1, window=1)
    cb = rate_limiter_module.CircuitBreaker(redis_client=backend, key="cb:test", threshold=1, window=1, cooldown=5)

    # Первый вызов разрешён, второй — блок
    assert await rate.is_allowed("u1") is True
    assert await rate.is_allowed("u1") is False
    await rate.reset("u1")
    assert await rate.is_allowed("u1") is True

    # Circuit открывается после ошибки
    assert await cb.is_open() is False
    await cb.record_failure()
    assert await cb.is_open() is True
    await cb.reset()
    assert await cb.is_open() is False

    # Проверяем fallback при ошибке Redis
    class _FailRedis:
        async def incr(self, *_: object, **__: object) -> int:  # pragma: no cover - исключения
            raise rate_limiter_module.RedisError("boom")

        async def expire(self, *_: object, **__: object) -> None:  # pragma: no cover - исключения
            raise rate_limiter_module.RedisError("boom")

        async def delete(self, *_: object, **__: object) -> None:  # pragma: no cover - исключения
            return None

    fallback_rate = rate_limiter_module.RateLimiter(redis_client=_FailRedis(), limit=1, window=1)  # type: ignore[arg-type]
    assert await fallback_rate.is_allowed("u2") is True
    assert await fallback_rate.is_allowed("u2") is False


def test_bot_runner_signal_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    from main import BotRunner

    called = []

    def _fake_signal(sig: int, handler: object) -> None:
        called.append(sig)

    monkeypatch.setattr(signal, "signal", _fake_signal)
    runner = BotRunner()
    runner.setup_signal_handlers()

    assert called  # обработчики сигнала установились


@pytest.mark.asyncio
async def test_command_handlers_start_help(
    fake_update: Any,
    fake_context: Any,
    async_retry_stub: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Мокируем AdminsStore, чтобы не требовался Postgres
    class _AdminNo:
        async def is_admin(self, _uid: int) -> bool:
            return False

        async def list_all_admins(self) -> list[int]:
            return []

    monkeypatch.setattr("bot.handlers.AdminsStore", _AdminNo)
    handler = CommandHandlers(image_generator=MagicMock(), next_run_provider=None)
    async_retry_stub(handler)

    await handler.start_command(fake_update, fake_context)
    await handler.help_command(fake_update, fake_context)

    assert fake_update.message.reply_text.await_count >= 2
    start_text = fake_update.message.reply_text.await_args_list[0].kwargs.get(
        "text",
        fake_update.message.reply_text.await_args_list[0].args[0],
    )
    assert "/start" in start_text
