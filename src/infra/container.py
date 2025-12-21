"""Composition root для сервисов бота.

Инкапсулирует сборку графа зависимостей backend‑части бота:
- формирует стек `ImageService` и связанные с ним доменные/инфраструктурные сервисы;
- создаёт контейнер `BotServices` для передачи зависимостей в хэндлеры и контроллеры;
- настраивает планировщик задач и вспомогательные application‑сервисы.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from bot.wednesday_bot import WednesdayBot

from app.admin_dashboard_service import AdminDashboardService
from app.api_status_service import APIStatusService
from app.database_operations_service import DatabaseOperationsService
from app.dispatch_execution_service import DispatchExecutionService
from app.dispatch_service import DispatchService
from app.fallback_service import FallbackService
from app.frog_limit_service import FrogRateLimiterService
from app.image_service import ImageService
from app.image_storage_unit_of_work import ImageStorageUnitOfWork
from app.prompt_service import PromptService
from app.target_preparation_service import TargetPreparationService
from domain.caption_service import CaptionService
from domain.image_generation import ImageGenerationService
from domain.prompt_generation import PromptGenerationService
from infra.cache.image_cache import ImageCacheService
from infra.cache.prompt_cache import PromptCache
from infra.cache.user_state_cache import UserStateCache
from infra.clients.factory import create_image_client, create_text_client
from infra.metrics.metrics import Metrics
from infra.metrics.metrics_recorder import MetricsRecorder
from infra.rate_limiting.circuit_breaker import CircuitBreakerService
from infra.rate_limiting.rate_limiter import RateLimiter
from infra.repos import ChatsRepo, ImagesRepo, ModelsRepo, PromptsRepo
from infra.repos.dispatch_registry import DispatchRegistry
from infra.repos.usage_tracker import UsageTracker
from infra.storage.image_storage import ImageStorageService
from shared.bot_services import BotServices
from shared.config import (
    AppSettings,
    Config,
    GigaChatConfig,
    ImageConfig,
    KandinskyConfig,
    PromptFallbackConfig,
)
from shared.protocols import (
    IChatsRepo,
    ICircuitBreaker,
    IMetrics,
    IModelsRepo,
    IRateLimiter,
    ITextToImageClient,
    ITextToTextClient,
    IUsageTracker,
)


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
    db_pool: asyncpg.Pool,
    image_client: ITextToImageClient | None = None,
    text_client: ITextToTextClient | None = None,
    models_repo: IModelsRepo | None = None,
) -> ImageService:
    """Собирает полный стек зависимостей для ImageService.

    Все клиенты, доменные и инфраструктурные сервисы создаются в одном месте,
    чтобы упростить дальнейшее сопровождение и тестирование.

    Args:
        config: Экземпляр Config для создания клиентов и чтения настроек.
        db_pool: Пул подключений PostgreSQL.
        image_client: Опциональный клиент для генерации изображений.
            Если None, создаётся новый через create_image_client().
        text_client: Опциональный клиент для генерации текста.
            Если None, создаётся новый через create_text_client().
        models_repo: Репозиторий моделей для передачи в клиенты через DI.

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
    fallback_config = PromptFallbackConfig(
        frog_prompts=list(ImageConfig.FROG_PROMPTS),
        styles=list(ImageConfig.STYLES),
    )
    prompt_generation = PromptGenerationService(
        text_client=text_client,
        fallback_config=fallback_config,
    )

    # Получаем Redis клиент явно
    from infra.redis.redis_client import get_redis

    redis_client = get_redis()

    # Инфраструктура
    images_repo = ImagesRepo(pool=db_pool)
    prompts_repo = PromptsRepo(pool=db_pool)
    image_cache = ImageCacheService(
        images_repo=images_repo,
        prompts_repo=prompts_repo,
    )
    image_storage = ImageStorageService()
    prompt_cache = PromptCache(redis_client=redis_client)

    # Получаем конфигурацию circuit breaker
    from shared.config import config

    cb_config = config.get_circuit_breaker_config()
    circuit_breaker: ICircuitBreaker = CircuitBreakerService(
        redis_client=redis_client,
        key="cb:kandinsky_api",
        threshold=cb_config.threshold,
        window=cb_config.window,
        cooldown=cb_config.cooldown,
    )
    metrics = MetricsRecorder()

    # Application‑сервисы
    prompt_service = PromptService(
        prompt_generation_service=prompt_generation,
        prompt_cache=prompt_cache,
    )

    # Создаём CaptionService из конфигурации
    caption_service = CaptionService(ImageConfig.CAPTIONS) if ImageConfig.CAPTIONS else None

    # Создаём UnitOfWork для управления сохранением изображений
    image_storage_uow = ImageStorageUnitOfWork(
        cache=image_cache,
        storage=image_storage,
    )

    return ImageService(
        image_generation_service=image_generation,
        prompt_service=prompt_service,
        caption_service=caption_service,
        image_cache=image_cache,
        image_storage=image_storage,
        circuit_breaker=circuit_breaker,
        metrics=metrics,
        storage_unit_of_work=image_storage_uow,
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
        models_repo: Репозиторий моделей для передачи в APIStatusService через DI.

    Returns:
        Экземпляр AdminDashboardService с внедрёнными зависимостями.
    """
    from infra.database.postgres_client import get_postgres_pool

    models_store = models_repo if models_repo is not None else ModelsRepo(pool=get_postgres_pool())

    # Создаём APIStatusService для инкапсуляции проверки статуса API
    api_status_service = APIStatusService(
        image_client=image_client,
        text_client=text_client,
        models_store=models_store,
    )

    return AdminDashboardService(
        usage=usage,
        chats=chats,
        metrics=metrics,
        api_status_service=api_status_service,
    )


def build_bot_services(config: Config, db_pool: asyncpg.Pool) -> BotServices:
    """Собирает контейнер BotServices для основного бота.

    На этом этапе:
    - image_service создаётся через build_image_stack();
    - остальные сервисы повторяют существующую инициализацию из WednesdayBot.

    Args:
        config: Экземпляр Config для создания сервисов и настроек.
        db_pool: Пул подключений PostgreSQL.

    Returns:
        Настроенный экземпляр BotServices.
    """

    app_settings = AppSettings.from_config(config)

    # Создаём ModelsRepo один раз для переиспользования во всех сервисах
    models_repo = ModelsRepo(pool=db_pool)

    # Создаём клиенты один раз для переиспользования во всех сервисах
    image_client, text_client = _create_clients(config, models_repo=models_repo)

    # Создаём image_service с переиспользованием клиентов
    image_service = build_image_stack(
        config=config,
        image_client=image_client,
        text_client=text_client,
        models_repo=models_repo,
        db_pool=db_pool,
    )

    usage = UsageTracker(
        pool=db_pool,
        monthly_quota=100,
        frog_threshold=70,
    )

    chats = ChatsRepo(pool=db_pool)
    dispatch_registry = DispatchRegistry(pool=db_pool)
    metrics = Metrics(pool=db_pool)

    # Получаем Redis клиент явно
    from infra.redis.redis_client import get_redis

    redis_client = get_redis()

    prompt_cache = PromptCache(redis_client=redis_client)
    user_state_store = UserStateCache(redis_client=redis_client)

    # Создаём rate limiters для команды /frog
    SECONDS_PER_MINUTE = 60
    global_limiter: IRateLimiter = RateLimiter(
        redis_client=redis_client,
        prefix="frog:global:",
        window=app_settings.frog_rate_limit_window_seconds,
        limit=app_settings.frog_rate_limit_max_requests,
    )
    user_limiter: IRateLimiter = RateLimiter(
        redis_client=redis_client,
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
    from app.frog_requests import FrogRequestService
    from infra.celery.celery_task_queue import CeleryTaskQueue

    # Создаём task queue и передаём в FrogRequestService
    task_queue = CeleryTaskQueue()
    frog_request_service = FrogRequestService(task_queue=task_queue)

    # Создаём сервисы для DispatchService
    target_preparation_service = TargetPreparationService(
        chats_repo=chats,
        dispatch_registry=dispatch_registry,
    )

    # Создаём MetricsRecorder для передачи в DatabaseOperationsService
    metrics_recorder = MetricsRecorder(metrics=metrics)

    # Создаём фабрику для Unit of Work
    from infra.database.database_unit_of_work import DatabaseUnitOfWork

    def create_unit_of_work() -> DatabaseUnitOfWork:
        return DatabaseUnitOfWork(pool=db_pool)

    # Создаём DatabaseOperationsService для атомарных операций БД
    database_operations = DatabaseOperationsService(
        dispatch_registry=dispatch_registry,
        usage_tracker=usage,
        metrics=metrics_recorder,
        unit_of_work_factory=create_unit_of_work,
    )

    dispatch_execution_service = DispatchExecutionService(
        dispatch_registry=dispatch_registry,
        metrics=metrics_recorder,
        usage_tracker=usage,
        database_operations=database_operations,
    )

    fallback_service = FallbackService(
        image_service=image_service,
        dispatch_execution_service=dispatch_execution_service,
        dispatch_registry=dispatch_registry,
        database_operations=database_operations,
        metrics=metrics_recorder,
    )

    dispatch_service = DispatchService(
        target_preparation_service=target_preparation_service,
        dispatch_execution_service=dispatch_execution_service,
        fallback_service=fallback_service,
        image_service=image_service,
    )

    admin_dashboard_service = build_admin_dashboard_service(
        usage=usage,
        chats=chats,
        metrics=metrics_recorder,
        image_client=image_client,
        text_client=text_client,
        models_repo=models_repo,
    )

    return BotServices(
        usage=usage,
        chats=chats,
        dispatch_registry=dispatch_registry,
        metrics=metrics_recorder,
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


def build_bot(config: Config, db_pool: asyncpg.Pool, services: BotServices | None = None) -> WednesdayBot:
    """Создаёт и настраивает экземпляр WednesdayBot.

    Единственная точка создания WednesdayBot в приложении. Использует
    Dependency Injection для передачи зависимостей в бот.

    Args:
        config: Экземпляр Config для создания сервисов и зависимостей.
        db_pool: Пул подключений PostgreSQL.
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
        services = build_bot_services(config, db_pool)

    # Создаём бот с внедрёнными зависимостями
    bot = WednesdayBot(services=services)

    # Обратная ссылка уже установлена в конструкторе бота,
    # но убеждаемся, что она корректна
    services.bot_controller = bot

    return bot
