"""Доменные сервисы генерации изображений и промптов."""

from __future__ import annotations

from domain.caption_service import CaptionService
from domain.image_generation import ImageGenerationService
from domain.prompt_generation import PromptGenerationService
from shared.config import ImageConfig, PromptFallbackConfig
from shared.protocols.clients import ITextToImageClient, ITextToTextClient


def build_image_generation_service(
    image_client: ITextToImageClient,
) -> ImageGenerationService:
    """Создаёт `ImageGenerationService` для генерации изображений."""
    return ImageGenerationService(image_client)


def build_prompt_generation_service(
    text_client: ITextToTextClient | None,
) -> PromptGenerationService:
    """Создаёт `PromptGenerationService` для генерации промптов.

    Если текстовый клиент отсутствует, используется fallback‑конфигурация.
    """
    fallback_config = PromptFallbackConfig(
        frog_prompts=list(ImageConfig.FROG_PROMPTS),
        styles=list(ImageConfig.STYLES),
    )
    return PromptGenerationService(
        text_client=text_client,
        fallback_config=fallback_config,
    )


def build_caption_service() -> CaptionService | None:
    """Создаёт `CaptionService` из конфигурации (если настроен)."""
    if ImageConfig.CAPTIONS:
        return CaptionService(ImageConfig.CAPTIONS)
    return None
