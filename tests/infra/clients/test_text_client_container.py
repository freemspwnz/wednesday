from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

import pytest

from infra.clients.client_manager import ClientManagementService
from infra.clients.models.status import APIStatusResult, SetModelResult
from infra.clients.text_client_container import TextClientContainer
from shared.config import GigaChatConfig
from shared.protocols import ITextToTextClient


class _ClosableMockTextClient(ITextToTextClient):
    """Простой мок текстового клиента с поддержкой aclose() для тестов контейнера."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.closed: bool = False
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, user_id: str | None = None) -> str:
        self.calls.append({"method": "generate", "prompt": prompt, "user_id": user_id})
        return f"{self.name}:{prompt}"

    async def check_api_status(self) -> APIStatusResult:
        self.calls.append({"method": "check_api_status"})
        return APIStatusResult.success(
            message=f"{self.name}:ok",
            models=[],
            current_model_id=None,
            current_model_name=None,
        )

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        self.calls.append({"method": "get_available_models", "save_models": save_models})
        return [f"{self.name}-model"]

    async def set_model(self, model_name: str) -> SetModelResult:
        self.calls.append({"method": "set_model", "model_name": model_name})
        return SetModelResult.ok(f"{self.name}:set:{model_name}")

    async def aclose(self) -> None:
        """Помечает клиента как закрытого."""
        self.closed = True


@pytest.mark.asyncio
async def test_container_delegates_calls_to_current_client() -> None:
    client = _ClosableMockTextClient("c1")
    container = TextClientContainer(initial_client=client)

    result_generate = await container.generate("hello", user_id="42")
    status_result = await container.check_api_status()
    models = await container.get_available_models(save_models=False)
    set_result = await container.set_model("TestModel")

    assert result_generate == "c1:hello"
    assert status_result.is_available is True
    assert "c1:ok" in status_result.message
    assert models == ["c1-model"]
    assert set_result.success is True
    assert "c1:set:TestModel" in set_result.message


@pytest.mark.asyncio
async def test_replace_client_closes_old_and_uses_new() -> None:
    old_client = _ClosableMockTextClient("old")
    new_client = _ClosableMockTextClient("new")
    container = TextClientContainer(initial_client=old_client)

    # Первый вызов идёт в старый клиент.
    result_old = await container.generate("prompt")
    assert result_old == "old:prompt"
    assert old_client.closed is False

    # Меняем клиента через ClientManagementService
    mock_client_manager = MagicMock(spec=ClientManagementService)
    mock_client_manager.create_text_client.return_value = new_client
    config = GigaChatConfig(authorization_key="test")
    mock_models_repo = MagicMock()
    await container.replace_client(
        config=config,
        client_manager=mock_client_manager,
        models_repo=mock_models_repo,
    )

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
    # После aclose клиент должен считаться неинициализированным и пробрасывать RuntimeError
    with pytest.raises(RuntimeError):
        await container.generate("x")
    with pytest.raises(RuntimeError):
        await container.check_api_status()
    assert await container.get_available_models() == []
    with pytest.raises(RuntimeError):
        await container.set_model("m")


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
        mock_client_manager = MagicMock(spec=ClientManagementService)
        mock_client_manager.create_text_client.return_value = new_client
        mock_models_repo = MagicMock()
        config = GigaChatConfig(authorization_key="test")
        await container.replace_client(
            config=config,
            client_manager=mock_client_manager,
            models_repo=mock_models_repo,
        )

    gen_task = asyncio.create_task(generate_loop())
    replace_task = asyncio.create_task(do_replace())

    results = await gen_task
    await replace_task

    # Все результаты либо от старого, либо от нового клиента; при этом старый
    # клиент по итогу должен быть закрыт.
    assert all(r in {"old:p", "new:p"} for r in results)
    assert old_client.closed is True
