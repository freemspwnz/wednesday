"""Конфигурация для fallback промптов."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptFallbackConfig:
    """Конфигурация для fallback промптов генерации изображений.

    Группирует связанные данные (промпты и стили) для использования
    в PromptGenerationService при генерации fallback промптов.
    """

    frog_prompts: list[str]
    styles: list[str]
