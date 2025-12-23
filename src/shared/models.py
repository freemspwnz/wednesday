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
