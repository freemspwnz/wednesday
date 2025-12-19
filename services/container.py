"""Composition root для сервисов бота.

Инкапсулирует сборку графа зависимостей backend‑части бота:
- формирует стек `ImageService` и связанные с ним доменные/инфраструктурные сервисы;
- создаёт контейнер `BotServices` для передачи зависимостей в хэндлеры и контроллеры;
- настраивает планировщик задач и вспомогательные application‑сервисы.
"""

from __future__ import annotations

import os

from services.app_settings import AppSettings
from services.application.admin_dashboard_service import AdminDashboardService
from services.application.dispatch_service import DispatchService
from services.application.frog_limit_service import FrogRateLimiterService
from services.application.frog_requests import FrogRequestService
from services.application.image_service import ImageService
from services.application.prompt_service import PromptService
from services.bot_services import BotServices
from services.clients.factory import create_image_client, create_text_client
from services.clients.interfaces import ITextToImageClient, ITextToTextClient
from services.domain.image_generation import ImageGenerationService
from services.domain.prompt_generation import PromptGenerationService
from services.infrastructure.cache.image_cache import ImageCacheService
from services.infrastructure.cache.prompt_cache import PromptCache
from services.infrastructure.cache.user_state_cache import UserStateCache
from services.infrastructure.metrics.metrics_recorder import MetricsRecorder
from services.infrastructure.rate_limiting.circuit_breaker import CircuitBreakerService
from services.infrastructure.rate_limiting.rate_limiter import RateLimiter
from services.infrastructure.storage.image_storage import ImageStorageService
from services.infrastructure.storage.prompt_storage import PromptStorageService
from services.protocols import ICircuitBreaker, IPromptStorage, IRateLimiter
from utils.chats_store import ChatsStore
from utils.config import ImageConfig, config
from utils.dispatch_registry import DispatchRegistry
from utils.metrics import Metrics
from utils.models_store import ModelsStore
from utils.usage_tracker import UsageTracker


def _create_clients(prompt_storage: IPromptStorage | None = None) -> tuple:
    """Создаёт клиенты для внешних ML‑сервисов.

    Args:
        prompt_storage: Опциональное хранилище промптов. Если None, создаётся новый экземпляр.

    Returns:
        Кортеж (image_client, text_client, prompt_storage) для использования в сервисах.
    """
    if prompt_storage is None:
        prompt_storage = PromptStorageService()
    image_client = create_image_client()
    text_client = create_text_client(prompt_storage=prompt_storage)
    return (image_client, text_client, prompt_storage)


def build_image_stack(
    image_client: ITextToImageClient | None = None,
    text_client: ITextToTextClient | None = None,
    prompt_storage: IPromptStorage | None = None,
) -> ImageService:
    """Собирает полный стек зависимостей для ImageService.

    Все клиенты, доменные и инфраструктурные сервисы создаются в одном месте,
    чтобы упростить дальнейшее сопровождение и тестирование.

    Args:
        image_client: Опциональный клиент для генерации изображений.
            Если None, создаётся новый через create_image_client().
        text_client: Опциональный клиент для генерации текста.
            Если None, создаётся новый через create_text_client().
        prompt_storage: Опциональное хранилище промптов.
            Если None, создаётся новый PromptStorageService.

    Returns:
        Настроенный экземпляр ImageService.
    """
    # Инфраструктура и клиенты
    if prompt_storage is None:
        prompt_storage = PromptStorageService()
    if image_client is None:
        image_client = create_image_client()
    if text_client is None:
        text_client = create_text_client(prompt_storage=prompt_storage)

    # Доменные сервисы
    image_generation = ImageGenerationService(image_client)
    prompt_generation = PromptGenerationService(text_client)

    # Инфраструктура
    image_cache = ImageCacheService()
    image_storage = ImageStorageService()
    prompt_cache = PromptCache()
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


def build_admin_dashboard_service(
    usage: UsageTracker,
    chats: ChatsStore,
    metrics: Metrics,
    image_client: ITextToImageClient,
    text_client: ITextToTextClient | None,
) -> AdminDashboardService:
    """Собирает AdminDashboardService с зависимостями.

    Args:
        usage: Трекер использования для статистики.
        chats: Хранилище чатов для получения списка активных чатов.
        metrics: Метрики производительности.
        image_client: Клиент для генерации изображений.
        text_client: Клиент для генерации текста.

    Returns:
        Экземпляр AdminDashboardService с внедрёнными зависимостями.
    """
    models_store = ModelsStore()
    return AdminDashboardService(
        usage=usage,
        chats=chats,
        metrics=metrics,
        image_client=image_client,
        text_client=text_client,
        models_store=models_store,
    )


def build_bot_services() -> BotServices:
    """Собирает контейнер BotServices для основного бота.

    На этом этапе:
    - image_service создаётся через build_image_stack();
    - остальные сервисы повторяют существующую инициализацию из WednesdayBot.
    """
    app_settings = AppSettings.from_config(config)

    # Создаём клиенты один раз для переиспользования во всех сервисах
    image_client, text_client, prompt_storage = _create_clients()

    # Создаём image_service с переиспользованием клиентов
    image_service = build_image_stack(
        image_client=image_client,
        text_client=text_client,
        prompt_storage=prompt_storage,
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

    # Создаём rate limiters для команды /frog
    SECONDS_PER_MINUTE = 60
    global_limiter: IRateLimiter = RateLimiter(
        prefix="frog:global:",
        window=app_settings.frog_rate_limit_window_seconds,
        limit=app_settings.frog_rate_limit_max_requests,
    )
    user_limiter: IRateLimiter = RateLimiter(
        prefix="frog:user:",
        window=app_settings.frog_rate_limit_minutes * SECONDS_PER_MINUTE,
        limit=1,
    )

    frog_rate_limiter = FrogRateLimiterService(
        settings=app_settings,
        global_limiter=global_limiter,
        user_limiter=user_limiter,
    )
    frog_request_service = FrogRequestService()
    dispatch_service = DispatchService(
        usage=usage,
        chats=chats,
        dispatch_registry=dispatch_registry,
        metrics=metrics,
        image_service=image_service,
    )

    admin_dashboard_service = build_admin_dashboard_service(
        usage=usage,
        chats=chats,
        metrics=metrics,
        image_client=image_client,
        text_client=text_client,
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
        bot_controller=None,
        dispatch_service=dispatch_service,
        admin_dashboard_service=admin_dashboard_service,
    )
