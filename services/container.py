"""Composition root для сервисов бота.

Содержит функции сборки графа зависимостей для backend‑части бота.

Спринт 1, задача 1.1:
- Ввести модуль сборки зависимостей и централизовать создание стека ImageService.
"""

from __future__ import annotations

from services.application.image_service import ImageService
from services.application.prompt_service import PromptService
from services.clients.factory import create_image_client, create_text_client
from services.domain.image_generation import ImageGenerationService
from services.domain.prompt_generation import PromptGenerationService
from services.infrastructure.cache.image_cache import ImageCacheService
from services.infrastructure.cache.prompt_cache import PromptCache
from services.infrastructure.metrics.metrics_recorder import MetricsRecorder
from services.infrastructure.rate_limiting.circuit_breaker import CircuitBreakerService
from services.infrastructure.storage.image_storage import ImageStorageService
from services.infrastructure.storage.prompt_storage import PromptStorageService
from utils.config import config


def build_image_stack() -> ImageService:
    """Собирает полный стек зависимостей для ImageService.

    Все клиенты, доменные и инфраструктурные сервисы создаются в одном месте,
    чтобы упростить дальнейшее сопровождение и тестирование.
    """
    # Клиенты
    image_client = create_image_client()
    text_client = create_text_client()

    # Доменные сервисы
    image_generation = ImageGenerationService(image_client)
    prompt_generation = PromptGenerationService(text_client)

    # Инфраструктура
    image_cache = ImageCacheService()
    image_storage = ImageStorageService()
    prompt_cache = PromptCache()
    prompt_storage = PromptStorageService()
    circuit_breaker = CircuitBreakerService(
        key="cb:kandinsky_api",
        threshold=5,
        window=300,
    )
    metrics = MetricsRecorder()

    # Application‑сервисы
    prompt_service = PromptService(
        prompt_generation_service=prompt_generation,
        prompt_cache=prompt_cache,
        prompt_storage=prompt_storage,
    )

    return ImageService(
        image_generation_service=image_generation,
        prompt_service=prompt_service,
        image_cache=image_cache,
        image_storage=image_storage,
        circuit_breaker=circuit_breaker,
        metrics=metrics,
        max_retries=config.max_retries,
    )
