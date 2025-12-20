"""Модели для результатов проверки статуса API."""

from __future__ import annotations

from dataclasses import dataclass


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

    @classmethod
    def ok(cls, message: str) -> SetModelResult:
        """Создаёт результат успешной установки модели."""
        return cls(success=True, message=message)

    @classmethod
    def error(cls, message: str) -> SetModelResult:
        """Создаёт результат ошибки установки модели."""
        return cls(success=False, message=message)
