"""
Тестовые реализации клиентов ML‑сервисов.

В этом модуле находятся простые моки для интерфейсов:

- `ITextToImageClient` — `MockTextToImageClient`;
- `ITextToTextClient` — `MockTextToTextClient`.

Основные цели:

- детерминированное поведение в юнит‑тестах (никаких реальных HTTP‑запросов);
- возможность проверять последовательность и параметры вызовов через `self.calls`;
- структурная совместимость с Protocol‑интерфейсами для строгой проверки mypy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.clients import ITextToImageClient, ITextToTextClient


@dataclass
class _Call:
    """Структура одного вызова mock‑клиента."""

    prompt: str
    user_id: str | None
    kwargs: dict[str, Any] = field(default_factory=dict)


class MockTextToImageClient(ITextToImageClient):
    """Мок‑клиент текст‑к‑изображению для юнит‑тестов.

    Сохраняет все вызовы в списке `calls` и возвращает заранее заданный результат.
    Позволяет:

    - проверять, что бизнес‑логика корректно формирует промпты;
    - эмулировать успешные и неуспешные ответы (через `set_response`).
    """

    def __init__(self) -> None:
        self.calls: list[_Call] = []
        self._response: bytes | None = b"mock-image-bytes"

    def set_response(self, value: bytes | None) -> None:
        """Задаёт байтовый результат, который будет возвращён generate()."""
        self._response = value

    async def generate(self, prompt: str, user_id: str | None = None) -> bytes | None:
        """Сохраняет параметры вызова и возвращает настроенный результат."""
        self.calls.append(_Call(prompt=prompt, user_id=user_id, kwargs={}))
        return self._response


class MockTextToTextClient(ITextToTextClient):
    """Мок‑клиент текст‑ту‑текст для юнит‑тестов.

    Аналогично `MockTextToImageClient`, но работает со строковым результатом.
    Реализует все методы интерфейса ITextToTextClient.
    """

    def __init__(
        self,
        generate_response: str | None = "mock-text",
        check_api_status_response: tuple[bool, str] = (True, "✅ Mock API доступен"),
        get_available_models_response: list[str] | None = None,
        set_model_response: tuple[bool, str] = (True, "✅ Mock модель установлена"),
    ) -> None:
        self.calls: list[_Call] = []
        self._generate_response: str | None = generate_response
        self._check_api_status_response: tuple[bool, str] = check_api_status_response
        self._get_available_models_response: list[str] = get_available_models_response or ["MockChat-1", "MockChat-2"]
        self._set_model_response: tuple[bool, str] = set_model_response

    def set_response(self, value: str | None) -> None:
        """Задаёт текстовый результат, который будет возвращён generate()."""
        self._generate_response = value

    async def generate(self, prompt: str, user_id: str | None = None) -> str | None:
        """Сохраняет параметры вызова и возвращает настроенный результат."""
        self.calls.append(_Call(prompt=prompt, user_id=user_id, kwargs={}))
        return self._generate_response

    async def check_api_status(self) -> tuple[bool, str]:
        """Мок проверки статуса API."""
        self.calls.append(_Call(prompt="check_api_status", user_id=None, kwargs={}))
        return self._check_api_status_response

    async def get_available_models(self, save_models: bool = True) -> list[str]:
        """Мок получения списка моделей."""
        self.calls.append(_Call(prompt="get_available_models", user_id=None, kwargs={"save_models": save_models}))
        return self._get_available_models_response

    async def set_model(self, model_name: str) -> tuple[bool, str]:
        """Мок установки модели."""
        self.calls.append(_Call(prompt="set_model", user_id=None, kwargs={"model_name": model_name}))
        return self._set_model_response
