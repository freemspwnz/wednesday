from __future__ import annotations

import asyncio
from typing import Any

import pytest

from services.clients.text_client_container import TextClientContainer
from services.protocols import ITextToTextClient


class _ClosableMockTextClient(ITextToTextClient):
    """Простой мок текстового клиента с поддержкой aclose() для тестов контейнера."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.closed: bool = False
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, user_id: str | None = None) -> str:
        self.calls.append({"method": "generate", "prompt": prompt, "user_id": user_id})
        return f"{self.name}:{prompt}"

    async def check_api_status(self) -> tuple[bool, str]:
        self.calls.append({"method": "check_api_status"})
        return True, f"{self.name}:ok"

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        self.calls.append({"method": "get_available_models", "save_models": save_models})
        return [f"{self.name}-model"]

    async def set_model(self, model_name: str) -> tuple[bool, str]:
        self.calls.append({"method": "set_model", "model_name": model_name})
        return True, f"{self.name}:set:{model_name}"

    async def aclose(self) -> None:
        """Помечает клиента как закрытого."""
        self.closed = True


@pytest.mark.asyncio
async def test_container_delegates_calls_to_current_client() -> None:
    client = _ClosableMockTextClient("c1")
    container = TextClientContainer(initial_client=client)

    result_generate = await container.generate("hello", user_id="42")
    status_ok, status_msg = await container.check_api_status()
    models = await container.get_available_models(save_models=False)
    set_ok, set_msg = await container.set_model("TestModel")

    assert result_generate == "c1:hello"
    assert status_ok is True
    assert "c1:ok" in status_msg
    assert models == ["c1-model"]
    assert set_ok is True
    assert "c1:set:TestModel" in set_msg


@pytest.mark.asyncio
async def test_replace_client_closes_old_and_uses_new() -> None:
    old_client = _ClosableMockTextClient("old")
    new_client = _ClosableMockTextClient("new")
    container = TextClientContainer(initial_client=old_client)

    # Первый вызов идёт в старый клиент.
    result_old = await container.generate("prompt")
    assert result_old == "old:prompt"
    assert old_client.closed is False

    # Меняем клиента.
    await container.replace_client(new_client)

    # Старый клиент должен быть закрыт, новый — использоваться для новых вызовов.
    assert old_client.closed is True
    result_new = await container.generate("prompt2")
    assert result_new == "new:prompt2"


@pytest.mark.asyncio
async def test_aclose_closes_current_client_and_detaches_it() -> None:
    client = _ClosableMockTextClient("c1")
    container = TextClientContainer(initial_client=client)

    await container.aclose()

    assert client.closed is True
    # После aclose клиент должен считаться неинициализированным и возвращать
    # безопасные значения.
    assert await container.generate("x") is None
    ok, _msg = await container.check_api_status()
    assert ok is False
    assert await container.get_available_models() == []
    ok_set, _msg_set = await container.set_model("m")
    assert ok_set is False


@pytest.mark.asyncio
async def test_replace_client_is_thread_safe_for_concurrent_calls() -> None:
    old_client = _ClosableMockTextClient("old")
    new_client = _ClosableMockTextClient("new")
    container = TextClientContainer(initial_client=old_client)

    async def generate_loop() -> list[str | None]:
        results: list[str | None] = []
        for _ in range(10):
            results.append(await container.generate("p"))
        return results

    async def do_replace() -> None:
        # Небольшая задержка, чтобы генерации начались до замены.
        await asyncio.sleep(0.01)
        await container.replace_client(new_client)

    gen_task = asyncio.create_task(generate_loop())
    replace_task = asyncio.create_task(do_replace())

    results = await gen_task
    await replace_task

    # Все результаты либо от старого, либо от нового клиента; при этом старый
    # клиент по итогу должен быть закрыт.
    assert all(r in {"old:p", "new:p"} for r in results)
    assert old_client.closed is True
