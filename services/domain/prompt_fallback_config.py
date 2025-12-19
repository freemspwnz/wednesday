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

    @classmethod
    def from_image_config(cls) -> PromptFallbackConfig:
        """Создает PromptFallbackConfig из глобального ImageConfig.

        Используется только в container.py при сборке зависимостей.
        """
        from utils.config import ImageConfig

        return cls(
            frog_prompts=list(ImageConfig.FROG_PROMPTS),
            styles=list(ImageConfig.STYLES),
        )
