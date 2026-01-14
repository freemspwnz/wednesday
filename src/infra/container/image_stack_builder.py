"""Сборка полного стека зависимостей для `ImageService`."""

from __future__ import annotations

from app.image_existence_service import ImageExistenceService
from app.image_generation_coordinator import ImageGenerationCoordinator
from app.image_service import ImageService
from app.image_storage_coordinator import ImageStorageCoordinator
from app.image_storage_unit_of_work import ImageStorageUnitOfWork
from app.prompt_service import PromptService
from domain.caption_service import CaptionService
from domain.image_generation import ImageGenerationService
from domain.prompt_generation import PromptGenerationService
from infra.cache.prompt_cache import PromptCache
from infra.storage.failed_cache_queue import FailedCacheQueue
from infra.storage.image_storage import ImageStorageService
from shared.config import ImageConfig, PromptFallbackConfig
from shared.protocols.clients import ITextToImageClient, ITextToTextClient
from shared.protocols.infrastructure import ICircuitBreaker, ILogger, IMetrics
from shared.protocols.repositories import IImageRepo, IPromptRepo


def build_image_storage_service(
    *,
    logger: ILogger,
) -> ImageStorageService:
    """Создаёт `ImageStorageService` для файлового хранилища изображений."""
    storage_logger = logger.bind(module="ImageStorageService")
    return ImageStorageService(logger=storage_logger)


def build_prompt_service(
    *,
    prompt_generation_service: PromptGenerationService,
    prompt_cache: PromptCache,
    logger: ILogger,
) -> PromptService:
    """Создаёт `PromptService` для работы с промптами."""
    prompt_logger = logger.bind(module="PromptService")
    return PromptService(
        prompt_generation_service=prompt_generation_service,
        prompt_cache=prompt_cache,
        logger=prompt_logger,
    )


def build_image_storage_uow(
    *,
    failed_cache_queue: FailedCacheQueue,
    image_existence_service: ImageExistenceService,
    image_storage: ImageStorageService,
    logger: ILogger,
) -> ImageStorageUnitOfWork:
    """Создаёт `ImageStorageUnitOfWork` для управления сохранением изображений."""
    uow_logger = logger.bind(module="ImageStorageUnitOfWork")
    return ImageStorageUnitOfWork(
        failed_cache_queue=failed_cache_queue,
        image_existence_service=image_existence_service,
        storage=image_storage,
        logger=uow_logger,
    )


def build_image_generation_coordinator(
    *,
    image_generation: ImageGenerationService,
    circuit_breaker: ICircuitBreaker,
    image_existence_service: ImageExistenceService,
    metrics: IMetrics,
    logger: ILogger,
) -> ImageGenerationCoordinator:
    """Создаёт `ImageGenerationCoordinator` для координации генерации изображений."""
    coord_logger = logger.bind(module="ImageGenerationCoordinator")
    return ImageGenerationCoordinator(
        generation_service=image_generation,
        circuit_breaker=circuit_breaker,
        image_existence_service=image_existence_service,
        metrics=metrics,
        logger=coord_logger,
    )


def build_image_storage_coordinator(
    *,
    image_storage_uow: ImageStorageUnitOfWork,
    metrics: IMetrics,
    logger: ILogger,
) -> ImageStorageCoordinator:
    """Создаёт `ImageStorageCoordinator` для координации хранения изображений."""
    coord_logger = logger.bind(module="ImageStorageCoordinator")
    return ImageStorageCoordinator(
        storage_unit_of_work=image_storage_uow,
        metrics=metrics,
        logger=coord_logger,
    )


def build_image_existence_service(
    *,
    prompts_repo: IPromptRepo,
    images_repo: IImageRepo,
    logger: ILogger,
) -> ImageExistenceService:
    """Создаёт сервис проверки существования изображений."""
    existence_logger = logger.bind(module="ImageExistenceService")
    return ImageExistenceService(
        prompts_repo=prompts_repo,
        images_repo=images_repo,
        logger=existence_logger,
    )


def build_image_stack(  # noqa: PLR0913
    *,
    image_client: ITextToImageClient,
    text_client: ITextToTextClient | None,
    prompt_cache: PromptCache,
    failed_cache_queue: FailedCacheQueue,
    prompts_repo: IPromptRepo,
    images_repo: IImageRepo,
    circuit_breaker: ICircuitBreaker,
    metrics: IMetrics,
    logger: ILogger,
) -> ImageService:
    """Собирает полный стек зависимостей для `ImageService`."""
    app_logger = logger.bind(module="ImageService")

    # Доменные сервисы
    image_generation = ImageGenerationService(image_client)
    fallback_config = PromptFallbackConfig(
        frog_prompts=list(ImageConfig.FROG_PROMPTS),
        styles=list(ImageConfig.STYLES),
    )
    prompt_generation = PromptGenerationService(
        text_client=text_client,
        fallback_config=fallback_config,
    )
    prompt_service = build_prompt_service(
        prompt_generation_service=prompt_generation,
        prompt_cache=prompt_cache,
        logger=logger,
    )
    caption_service: CaptionService | None = CaptionService(ImageConfig.CAPTIONS) if ImageConfig.CAPTIONS else None

    # Инфраструктура и application‑сервисы
    image_storage = build_image_storage_service(logger=logger)
    image_existence_service = build_image_existence_service(
        prompts_repo=prompts_repo,
        images_repo=images_repo,
        logger=logger,
    )
    image_storage_uow = build_image_storage_uow(
        failed_cache_queue=failed_cache_queue,
        image_existence_service=image_existence_service,
        image_storage=image_storage,
        logger=logger,
    )
    generation_coordinator = build_image_generation_coordinator(
        image_generation=image_generation,
        circuit_breaker=circuit_breaker,
        image_existence_service=image_existence_service,
        metrics=metrics,
        logger=logger,
    )
    storage_coordinator = build_image_storage_coordinator(
        image_storage_uow=image_storage_uow,
        metrics=metrics,
        logger=logger,
    )

    return ImageService(
        prompt_service=prompt_service,
        generation_coordinator=generation_coordinator,
        storage_coordinator=storage_coordinator,
        image_storage=image_storage,
        caption_service=caption_service,
        logger=app_logger,
    )
