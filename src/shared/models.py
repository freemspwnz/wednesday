from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict


@dataclass(frozen=True)
class APIStatusResult:
    """Результат проверки статуса API."""

    is_available: bool
    message: str
    models: list[str]
    current_model_id: str | None
    current_model_name: str | None

    @classmethod
    def success(
        cls,
        message: str,
        models: list[str],
        current_model_id: str | None = None,
        current_model_name: str | None = None,
    ) -> APIStatusResult:
        """Создаёт результат успешной проверки."""
        return cls(
            is_available=True,
            message=message,
            models=models,
            current_model_id=current_model_id,
            current_model_name=current_model_name,
        )


@dataclass(frozen=True)
class SetModelResult:
    """Результат установки модели."""

    success: bool
    message: str
    model_id: str | None = None
    model_name: str | None = None

    @classmethod
    def ok(
        cls,
        message: str,
        model_id: str | None = None,
        model_name: str | None = None,
    ) -> SetModelResult:
        """Создаёт результат успешной установки модели."""
        return cls(success=True, message=message, model_id=model_id, model_name=model_name)

    @classmethod
    def error(cls, message: str) -> SetModelResult:
        """Создаёт результат ошибки установки модели."""
        return cls(success=False, message=message, model_id=None, model_name=None)


@dataclass(frozen=True)
class ImageRecordDTO:
    """DTO записи изображения для использования в протоколах и сервисах.

    Используется как общий контракт между слоями app/shared и infra
    без привязки к конкретной реализации репозитория.
    """

    id: int
    image_hash: str
    prompt_hash: str
    path: str
    created_at: datetime


@dataclass(frozen=True)
class PromptRecordDTO:
    """DTO записи промпта для использования в протоколах и сервисах.

    Используется как общий контракт между слоями app/shared и infra
    без привязки к конкретной реализации репозитория.
    """

    id: int
    raw_text: str
    normalized_text: str
    prompt_hash: str
    created_at: datetime
    ab_group: str | None


class FrogRequestResult(TypedDict):
    """Типизированный результат обработки запроса генерации жабы.

    Использует TypedDict для неизменяемой структуры данных (только для передачи).
    Стандарт: TypedDict для неизменяемых структур, Dataclass для мутабельных DTO.

    Attributes:
        status: Статус обработки запроса ("success" или "failed").
        error: Описание ошибки, если status="failed", иначе None.
    """

    status: Literal["success", "failed"]
    error: str | None
