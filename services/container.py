"""Composition root для сервисов бота.

Инкапсулирует сборку графа зависимостей backend‑части бота:
- формирует стек `ImageService` и связанные с ним доменные/инфраструктурные сервисы;
- создаёт контейнер `BotServices` для передачи зависимостей в хэндлеры и контроллеры;
- настраивает планировщик задач и вспомогательные application‑сервисы.
"""

from __future__ import annotations

import os

from services.app_settings import AppSettings
from services.application.dispatch_service import DispatchService
from services.application.frog_limit_service import FrogRateLimiterService
from services.application.frog_requests import FrogRequestService
from services.application.image_service import ImageService
from services.application.prompt_service import PromptService
from services.bot_services import BotServices
from services.clients.factory import create_image_client, create_text_client
from services.domain.image_generation import ImageGenerationService
from services.domain.prompt_generation import PromptGenerationService
from services.infrastructure.cache.image_cache import ImageCacheService
from services.infrastructure.cache.prompt_cache import PromptCache
from services.infrastructure.cache.user_state_cache import UserStateCache
from services.infrastructure.metrics.metrics_recorder import MetricsRecorder
from services.infrastructure.rate_limiting.circuit_breaker import CircuitBreakerService
from services.infrastructure.storage.image_storage import ImageStorageService
from services.infrastructure.storage.prompt_storage import PromptStorageService
from services.protocols import ICircuitBreaker, IScheduler
from services.scheduler import TaskScheduler
from utils.chats_store import ChatsStore
from utils.config import ImageConfig, config
from utils.dispatch_registry import DispatchRegistry
from utils.metrics import Metrics
from utils.usage_tracker import UsageTracker


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
    circuit_breaker: ICircuitBreaker = CircuitBreakerService(
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
        captions=ImageConfig.CAPTIONS,
    )


def build_bot_services() -> BotServices:
    """Собирает контейнер BotServices для основного бота.

    На этом этапе:
    - image_service создаётся через build_image_stack();
    - остальные сервисы повторяют существующую инициализацию из WednesdayBot.
    """
    app_settings = AppSettings.from_config(config)
    image_service = build_image_stack()

    scheduler: IScheduler | None = (
        TaskScheduler(
            send_times=config.scheduler_send_times,
            wednesday_day=config.scheduler_wednesday_day,
            check_interval=30,
            timezone=config.scheduler_tz or "Europe/Moscow",
        )
        if config.use_old_scheduler
        else None
    )

    usage = UsageTracker(
        storage_path=os.getenv("USAGE_STORAGE", "usage_stats.json"),
        monthly_quota=100,
        frog_threshold=70,
    )

    chats = ChatsStore()
    dispatch_registry = DispatchRegistry()
    metrics = Metrics()
    prompt_cache = PromptCache()
    user_state_store = UserStateCache()
    frog_rate_limiter = FrogRateLimiterService(settings=app_settings)
    frog_request_service = FrogRequestService()
    dispatch_service = DispatchService(
        usage=usage,
        chats=chats,
        dispatch_registry=dispatch_registry,
        metrics=metrics,
        image_service=image_service,
    )

    return BotServices(
        usage=usage,
        chats=chats,
        dispatch_registry=dispatch_registry,
        metrics=metrics,
        prompt_cache=prompt_cache,
        user_state_store=user_state_store,
        settings=app_settings,
        image_service=image_service,
        frog_rate_limiter=frog_rate_limiter,
        frog_request_service=frog_request_service,
        scheduler=scheduler,
        bot_controller=None,
        dispatch_service=dispatch_service,
    )
