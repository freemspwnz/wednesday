from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest

from services.clients.image_client_container import ImageClientContainer
from services.clients.models.status import APIStatusResult, SetModelResult
from services.protocols import ITextToImageClient


class _ClosableMockImageClient(ITextToImageClient):
    """Простой мок клиента генерации изображений с поддержкой aclose() для тестов контейнера."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.closed: bool = False
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, user_id: str | None = None) -> bytes:
        self.calls.append({"method": "generate", "prompt": prompt, "user_id": user_id})
        return f"{self.name}:{prompt}".encode()

    async def check_api_status(self, save_models: bool = True) -> APIStatusResult:
        self.calls.append({"method": "check_api_status", "save_models": save_models})
        return APIStatusResult.success(
            message=f"{self.name}:ok",
            models=[f"{self.name}-model"],
            current_model_id=f"{self.name}-id",
            current_model_name=f"{self.name}-name",
        )

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        self.calls.append({"method": "get_available_models", "save_models": save_models})
        return [f"{self.name}-model"]

    async def set_model(self, model_identifier: str) -> SetModelResult:
        self.calls.append({"method": "set_model", "model_identifier": model_identifier})
        return SetModelResult.ok(f"{self.name}:set:{model_identifier}")

    async def aclose(self) -> None:
        """Помечает клиента как закрытого."""
        self.closed = True


@pytest.mark.asyncio
async def test_container_delegates_calls_to_current_client() -> None:
    client = _ClosableMockImageClient("c1")
    container = ImageClientContainer(initial_client=client)

    result_generate = await container.generate("hello", user_id="42")
    status_result = await container.check_api_status(save_models=False)
    available_models = await container.get_available_models(save_models=False)
    set_result = await container.set_model("TestModel")

    assert result_generate == b"c1:hello"
    assert status_result.is_available is True
    assert "c1:ok" in status_result.message
    assert status_result.models == ["c1-model"]
    assert status_result.current_model_id == "c1-id"
    assert status_result.current_model_name == "c1-name"
    assert available_models == ["c1-model"]
    assert set_result.success is True
    assert "c1:set:TestModel" in set_result.message


@pytest.mark.asyncio
async def test_replace_client_closes_old_and_uses_new() -> None:
    old_client = _ClosableMockImageClient("old")
    new_client = _ClosableMockImageClient("new")
    container = ImageClientContainer(initial_client=old_client)

    # Первый вызов идёт в старый клиент.
    result_old = await container.generate("prompt")
    assert result_old == b"old:prompt"
    assert old_client.closed is False

    # Меняем клиента.
    await container.replace_client(new_client)

    # Старый клиент должен быть закрыт, новый — использоваться для новых вызовов.
    assert old_client.closed is True
    result_new = await container.generate("prompt2")
    assert result_new == b"new:prompt2"


@pytest.mark.asyncio
async def test_aclose_closes_current_client_and_detaches_it() -> None:
    client = _ClosableMockImageClient("c1")
    container = ImageClientContainer(initial_client=client)

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
    old_client = _ClosableMockImageClient("old")
    new_client = _ClosableMockImageClient("new")
    container = ImageClientContainer(initial_client=old_client)

    async def generate_loop() -> list[bytes | None]:
        results: list[bytes | None] = []
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
    assert all(r in {b"old:p", b"new:p"} for r in results)
    assert old_client.closed is True


@pytest.mark.asyncio
async def test_container_handles_client_without_optional_methods() -> None:
    """Тест проверяет поведение контейнера с клиентом без опциональных методов."""

    class _MinimalImageClient:
        """Минимальная реализация только с обязательным методом generate.

        Остальные методы интерфейса отсутствуют, поэтому контейнер должен
        определять это через hasattr и возвращать безопасные значения.
        """

        async def generate(self, prompt: str, user_id: str | None = None) -> bytes:
            return b"minimal-result"

    # Используем cast для создания клиента без всех методов Protocol
    # Это нужно для тестирования поведения контейнера с клиентами, которые
    # не поддерживают опциональные методы
    minimal_client = _MinimalImageClient()
    client = cast(ITextToImageClient, minimal_client)
    container = ImageClientContainer(initial_client=client)

    # generate должен работать
    result = await container.generate("test")
    assert result == b"minimal-result"

    # Опциональные методы должны пробрасывать RuntimeError, так как
    # контейнер проверяет hasattr и определяет, что методы отсутствуют
    with pytest.raises(RuntimeError) as exc_info:
        await container.check_api_status()
    assert "не поддерживает" in str(exc_info.value)

    assert await container.get_available_models() == []

    with pytest.raises(RuntimeError) as exc_info:
        await container.set_model("test")
    assert "не поддерживает" in str(exc_info.value)


def test_set_initial_client_only_works_when_no_client() -> None:
    """Тест проверяет, что set_initial_client работает только при отсутствии клиента."""

    client1 = _ClosableMockImageClient("c1")
    client2 = _ClosableMockImageClient("c2")
    container = ImageClientContainer()

    # Устанавливаем первый клиент
    container.set_initial_client(client1)
    assert container.get_client() is client1

    # Попытка установить второй клиент должна быть проигнорирована
    container.set_initial_client(client2)
    assert container.get_client() is client1  # Остаётся первый клиент

    # Попытка установить None тоже должна быть проигнорирована
    container.set_initial_client(None)
    assert container.get_client() is client1  # Всё ещё первый клиент


@pytest.mark.asyncio
async def test_replace_client_with_none_removes_client() -> None:
    """Тест проверяет замену клиента на None."""
    client = _ClosableMockImageClient("c1")
    container = ImageClientContainer(initial_client=client)

    assert container.get_client() is client
    assert await container.generate("test") == b"c1:test"

    # Заменяем на None
    await container.replace_client(None)

    assert container.get_client() is None
    assert await container.generate("test") is None


@pytest.mark.asyncio
async def test_container_logs_warning_when_client_not_initialized() -> None:
    """Тест проверяет, что контейнер корректно обрабатывает отсутствие клиента."""
    container = ImageClientContainer()

    # Все методы должны пробрасывать RuntimeError при отсутствии клиента
    with pytest.raises(RuntimeError):
        await container.generate("test")
    with pytest.raises(RuntimeError) as exc_info:
        await container.check_api_status()
    assert "не инициализирован" in str(exc_info.value)
    assert await container.get_available_models() == []
    with pytest.raises(RuntimeError) as exc_info:
        await container.set_model("test")
    assert "не инициализирован" in str(exc_info.value)


@pytest.mark.asyncio
async def test_replace_client_handles_aclose_exception_gracefully() -> None:
    """Тест проверяет, что ошибки при закрытии старого клиента не ломают замену."""

    class _FailingCloseClient(_ClosableMockImageClient):
        """Клиент, который бросает исключение при закрытии."""

        async def aclose(self) -> None:
            raise RuntimeError("Failed to close")

    old_client = _FailingCloseClient("old")
    new_client = _ClosableMockImageClient("new")
    container = ImageClientContainer(initial_client=old_client)

    # Замена должна пройти успешно, даже если закрытие старого клиента упало
    await container.replace_client(new_client)

    # Новый клиент должен работать
    result = await container.generate("test")
    assert result == b"new:test"


def test_get_image_client_container_returns_singleton() -> None:
    """Тест проверяет, что get_image_client_container возвращает singleton."""
    from services.clients.image_client_container import get_image_client_container

    container1 = get_image_client_container()
    container2 = get_image_client_container()

    # Должен возвращаться один и тот же экземпляр
    assert container1 is container2


@pytest.mark.asyncio
async def test_aclose_handles_client_without_aclose_method() -> None:
    """Тест проверяет, что aclose работает с клиентами без метода aclose."""

    class _NoCloseClient(ITextToImageClient):
        """Клиент без метода aclose."""

        async def generate(self, prompt: str, user_id: str | None = None) -> bytes:
            return b"no-close-result"

        async def check_api_status(self, save_models: bool = True) -> APIStatusResult:
            return APIStatusResult.success(
                message="Not implemented",
                models=[],
                current_model_id=None,
                current_model_name=None,
            )

        async def get_available_models(self, save_models: bool = True) -> list[str]:
            return []

        async def set_model(self, model_identifier: str) -> SetModelResult:
            return SetModelResult.error("Not implemented")

    client = _NoCloseClient()
    container = ImageClientContainer(initial_client=client)

    # aclose должен завершиться без ошибок, даже если у клиента нет метода aclose
    await container.aclose()

    # После aclose клиент должен быть отключен
    assert container.get_client() is None
    assert await container.generate("test") is None


@pytest.mark.asyncio
async def test_get_client_returns_current_client() -> None:
    """Тест проверяет, что get_client возвращает текущий активный клиент."""
    client = _ClosableMockImageClient("c1")
    container = ImageClientContainer()

    assert container.get_client() is None

    container.set_initial_client(client)
    assert container.get_client() is client

    new_client = _ClosableMockImageClient("c2")
    await container.replace_client(new_client)
    assert container.get_client() is new_client
