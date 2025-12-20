"""Composition root для сервисов бота.

Инкапсулирует сборку графа зависимостей backend‑части бота:
- формирует стек `ImageService` и связанные с ним доменные/инфраструктурные сервисы;
- создаёт контейнер `BotServices` для передачи зависимостей в хэндлеры и контроллеры;
- настраивает планировщик задач и вспомогательные application‑сервисы.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.wednesday_bot import WednesdayBot

from services.application.admin_dashboard_service import AdminDashboardService
from services.application.dispatch_service import DispatchService
from services.application.frog_limit_service import FrogRateLimiterService
from services.application.image_service import ImageService
from services.application.prompt_service import PromptService
from services.bot_services import BotServices
from services.clients.factory import create_image_client, create_text_client
from services.domain.image_generation import ImageGenerationService
from services.domain.prompt_fallback_config import PromptFallbackConfig
from services.domain.prompt_generation import PromptGenerationService
from services.infrastructure.cache.image_cache import ImageCacheService
from services.infrastructure.cache.prompt_cache import PromptCache
from services.infrastructure.cache.user_state_cache import UserStateCache
from services.infrastructure.metrics.metrics_recorder import MetricsRecorder
from services.infrastructure.rate_limiting.circuit_breaker import CircuitBreakerService
from services.infrastructure.rate_limiting.rate_limiter import RateLimiter
from services.infrastructure.storage.image_storage import ImageStorageService
from services.protocols import (
    IChatsRepo,
    ICircuitBreaker,
    IMetrics,
    IModelsRepo,
    IRateLimiter,
    ITextToImageClient,
    ITextToTextClient,
    IUsageTracker,
)
from utils.chats_repo import ChatsRepo
from utils.config import AppSettings, Config, GigaChatConfig, ImageConfig, KandinskyConfig
from utils.dispatch_registry import DispatchRegistry
from utils.images_repo import ImagesRepo
from utils.metrics import Metrics
from utils.models_repo import ModelsRepo
from utils.prompts_repo import PromptsRepo
from utils.usage_tracker import UsageTracker


def _create_clients(config: Config, models_repo: IModelsRepo | None = None) -> tuple:
    """Создаёт клиенты для внешних ML‑сервисов.

    Args:
        config: Экземпляр Config для создания конфигураций клиентов.
        models_repo: Репозиторий моделей для передачи в клиенты через DI.

    Returns:
        Кортеж (image_client, text_client) для использования в сервисах.
    """
    # Создаем конфигурации из переданного config
    gigachat_config = GigaChatConfig.from_config(config)
    kandinsky_config = KandinskyConfig.from_config(config)

    # Передаем в фабрики
    image_client = create_image_client(kandinsky_config=kandinsky_config, models_repo=models_repo)
    text_client = create_text_client(gigachat_config=gigachat_config, models_repo=models_repo)
    return (image_client, text_client)


def build_image_stack(
    config: Config,
    image_client: ITextToImageClient | None = None,
    text_client: ITextToTextClient | None = None,
    models_repo: IModelsRepo | None = None,
) -> ImageService:
    """Собирает полный стек зависимостей для ImageService.

    Все клиенты, доменные и инфраструктурные сервисы создаются в одном месте,
    чтобы упростить дальнейшее сопровождение и тестирование.

    Args:
        config: Экземпляр Config для создания клиентов и чтения настроек.
        image_client: Опциональный клиент для генерации изображений.
            Если None, создаётся новый через create_image_client().
        text_client: Опциональный клиент для генерации текста.
            Если None, создаётся новый через create_text_client().

    Returns:
        Настроенный экземпляр ImageService.
    """
    # Инфраструктура и клиенты
    if image_client is None or text_client is None:
        # Используем _create_clients() вместо дублирования логики
        created_image_client, created_text_client = _create_clients(config, models_repo=models_repo)
        if image_client is None:
            image_client = created_image_client
        if text_client is None:
            text_client = created_text_client

    # Доменные сервисы
    image_generation = ImageGenerationService(image_client)
    fallback_config = PromptFallbackConfig.from_image_config()
    prompt_generation = PromptGenerationService(
        text_client=text_client,
        fallback_config=fallback_config,
    )

    # Инфраструктура
    images_repo = ImagesRepo()
    prompts_repo = PromptsRepo()
    image_cache = ImageCacheService(
        images_repo=images_repo,
        prompts_repo=prompts_repo,
    )
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


def build_admin_dashboard_service(  # noqa: PLR0913, PLR0917
    usage: IUsageTracker,
    chats: IChatsRepo,
    metrics: IMetrics,
    image_client: ITextToImageClient,
    text_client: ITextToTextClient | None,
    models_repo: IModelsRepo | None = None,
) -> AdminDashboardService:
    """Собирает AdminDashboardService с зависимостями.

    Args:
        usage: Трекер использования для статистики.
        chats: Хранилище чатов для получения списка активных чатов.
        metrics: Метрики производительности.
        image_client: Клиент для генерации изображений.
        text_client: Клиент для генерации текста.
        models_repo: Репозиторий моделей для передачи в сервис через DI.

    Returns:
        Экземпляр AdminDashboardService с внедрёнными зависимостями.
    """
    models_store = models_repo if models_repo is not None else ModelsRepo()
    return AdminDashboardService(
        usage=usage,
        chats=chats,
        metrics=metrics,
        image_client=image_client,
        text_client=text_client,
        models_store=models_store,
    )


def build_bot_services(config: Config) -> BotServices:
    """Собирает контейнер BotServices для основного бота.

    На этом этапе:
    - image_service создаётся через build_image_stack();
    - остальные сервисы повторяют существующую инициализацию из WednesdayBot.

    Args:
        config: Экземпляр Config для создания сервисов и настроек.

    Returns:
        Настроенный экземпляр BotServices.
    """
    app_settings = AppSettings.from_config(config)

    # Создаём ModelsRepo один раз для переиспользования во всех сервисах
    models_repo = ModelsRepo()

    # Создаём клиенты один раз для переиспользования во всех сервисах
    image_client, text_client = _create_clients(config, models_repo=models_repo)

    # Создаём image_service с переиспользованием клиентов
    image_service = build_image_stack(
        config=config,
        image_client=image_client,
        text_client=text_client,
        models_repo=models_repo,
    )

    usage = UsageTracker(
        storage_path=os.getenv("USAGE_STORAGE", "usage_stats.json"),
        monthly_quota=100,
        frog_threshold=70,
    )

    chats = ChatsRepo()
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
    # Ленивые импорты для избежания циклических зависимостей
    from services.application.frog_requests import FrogRequestService
    from services.infrastructure.celery.celery_task_queue import CeleryTaskQueue

    # Создаём task queue и передаём в FrogRequestService
    task_queue = CeleryTaskQueue()
    frog_request_service = FrogRequestService(task_queue=task_queue)
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
        models_repo=models_repo,
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


def build_bot(config: Config, services: BotServices | None = None) -> WednesdayBot:
    """Создаёт и настраивает экземпляр WednesdayBot.

    Единственная точка создания WednesdayBot в приложении. Использует
    Dependency Injection для передачи зависимостей в бот.

    Args:
        config: Экземпляр Config для создания сервисов и зависимостей.
        services: Опциональный контейнер сервисов. Если None, создаётся
            новый через build_bot_services().

    Returns:
        Настроенный экземпляр WednesdayBot с внедрёнными зависимостями.

    Note:
        Эта функция является Composition Root для WednesdayBot. Все зависимости
        создаются здесь и передаются в бот через конструктор.
    """
    # Ленивый импорт для избежания циклических зависимостей
    from bot.wednesday_bot import WednesdayBot

    if services is None:
        services = build_bot_services(config)

    # Создаём бот с внедрёнными зависимостями
    bot = WednesdayBot(services=services)

    # Обратная ссылка уже установлена в конструкторе бота,
    # но убеждаемся, что она корректна
    services.bot_controller = bot

    return bot
