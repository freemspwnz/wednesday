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
from app.model_management_service import ModelManagementService
from app.prompt_service import PromptService
from app.target_preparation_service import TargetPreparationService
from domain.caption_service import CaptionService
from domain.image_generation import ImageGenerationService
from domain.prompt_generation import PromptGenerationService
from infra.cache.image_cache import ImageCacheService
from infra.cache.prompt_cache import PromptCache
from infra.cache.user_state_cache import UserStateCache
from infra.clients.client_manager import ClientManagementService
from infra.clients.image_client_container import get_image_client_container
from infra.clients.text_client_container import get_text_client_container
from infra.logging.logger import get_logger
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
    Config,
    ImageConfig,
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


def _create_clients(
    config: Config,
    models_repo: IModelsRepo | None = None,
) -> tuple[ITextToImageClient, ITextToTextClient | None]:
    """Создаёт клиенты для внешних ML‑сервисов через Dependency Injection.

    Клиенты создаются через ClientManagementService и регистрируются в контейнерах
    для поддержки runtime-замены и корректного cleanup.

    Args:
        config: Экземпляр Config для создания конфигураций клиентов.
        models_repo: Репозиторий моделей для передачи в клиенты через DI.
            Если None, создаётся новый ModelsRepo с пулом из get_postgres_pool().

    Returns:
        Кортеж (image_client_container, text_client_container | None).
        Контейнеры реализуют интерфейсы ITextToImageClient и ITextToTextClient
        и обеспечивают runtime-замену клиентов.
    """
    # Создаём models_repo, если не передан
    if models_repo is None:
        from infra.database.postgres_client import get_postgres_pool
        from infra.repos import ModelsRepo

        models_repo = ModelsRepo(pool=get_postgres_pool())

    # Создаём сервис управления клиентами
    client_manager = ClientManagementService(models_repo=models_repo)

    # Создаём клиенты через DI
    kandinsky_config = config.kandinsky
    image_client = client_manager.create_image_client(
        config=kandinsky_config,
        models_repo=models_repo,
    )

    # Регистрируем в контейнере
    image_container = get_image_client_container()
    image_container.set_initial_client(image_client)

    # Создаём текстовый клиент, если настроен
    text_container: ITextToTextClient | None = None
    gigachat_config = config.gigachat
    if gigachat_config.authorization_key:
        text_client = client_manager.create_text_client(
            config=gigachat_config,
            models_repo=models_repo,
        )
        if text_client is not None:
            text_container_instance = get_text_client_container()
            text_container_instance.set_initial_client(text_client)
            text_container = text_container_instance

    return (image_container, text_container)


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
            Если None, создаётся новый через DI в _create_clients().
        text_client: Опциональный клиент для генерации текста.
            Если None, создаётся новый через DI в _create_clients().
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

    # Создаём общий логгер для всех сервисов
    app_logger = get_logger("app")

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
        logger=app_logger,
    )
    image_storage = ImageStorageService(logger=app_logger)
    prompt_cache = PromptCache(redis_client=redis_client)

    # Получаем конфигурацию circuit breaker
    cb_config = config.circuit_breaker
    circuit_breaker: ICircuitBreaker = CircuitBreakerService(
        redis_client=redis_client,
        key="cb:kandinsky_api",
        threshold=cb_config.threshold,
        window=cb_config.window,
        cooldown=cb_config.cooldown,
    )
    metrics = MetricsRecorder(logger=app_logger)

    # Application‑сервисы
    prompt_service = PromptService(
        prompt_generation_service=prompt_generation,
        prompt_cache=prompt_cache,
        logger=app_logger,
    )

    # Создаём CaptionService из конфигурации
    caption_service = None
    if ImageConfig.CAPTIONS:
        caption_service = CaptionService(ImageConfig.CAPTIONS)

    # Создаём UnitOfWork для управления сохранением изображений
    image_storage_uow = ImageStorageUnitOfWork(
        cache=image_cache,
        storage=image_storage,
        logger=app_logger,
    )

    return ImageService(
        image_generation_service=image_generation,
        prompt_service=prompt_service,
        storage_unit_of_work=image_storage_uow,
        caption_service=caption_service,
        image_cache=image_cache,
        image_storage=image_storage,
        circuit_breaker=circuit_breaker,
        metrics=metrics,
        logger=app_logger,
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

    # Создаём общий логгер для всех сервисов
    app_logger = get_logger("app")

    # Создаём APIStatusService для инкапсуляции проверки статуса API
    api_status_service = APIStatusService(
        image_client=image_client,
        text_client=text_client,
        models_store=models_store,
        logger=app_logger,
    )

    return AdminDashboardService(
        usage=usage,
        chats=chats,
        metrics=metrics,
        api_status_service=api_status_service,
        logger=app_logger,
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

    # Создаём AppSettings из Config
    from shared.config import AppSettings

    app_settings = AppSettings()

    # Создаём общий логгер для всех сервисов
    app_logger = get_logger("app")

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
        logger=app_logger,
    )
    # Ленивые импорты для избежания циклических зависимостей
    from app.frog_requests import FrogRequestService
    from infra.celery.celery_task_queue import CeleryTaskQueue

    # Создаём task queue и передаём в FrogRequestService
    task_queue = CeleryTaskQueue()
    frog_request_service = FrogRequestService(task_queue=task_queue, logger=app_logger)

    # Создаём сервисы для DispatchService
    target_preparation_service = TargetPreparationService(
        chats_repo=chats,
        dispatch_registry=dispatch_registry,
        logger=app_logger,
    )

    # Создаём MetricsRecorder для передачи в DatabaseOperationsService
    metrics_recorder = MetricsRecorder(metrics=metrics, logger=app_logger)

    # Создаём фабрику для Unit of Work
    from infra.database.database_unit_of_work import DatabaseUnitOfWork

    def create_unit_of_work() -> DatabaseUnitOfWork:
        return DatabaseUnitOfWork(pool=db_pool, logger=app_logger)

    # Создаём DatabaseOperationsService для атомарных операций БД
    database_operations = DatabaseOperationsService(
        dispatch_registry=dispatch_registry,
        usage_tracker=usage,
        metrics=metrics_recorder,
        unit_of_work_factory=create_unit_of_work,
        logger=app_logger,
    )

    dispatch_execution_service = DispatchExecutionService(
        dispatch_registry=dispatch_registry,
        metrics=metrics_recorder,
        usage_tracker=usage,
        database_operations=database_operations,
        logger=app_logger,
    )

    fallback_service = FallbackService(
        image_service=image_service,
        dispatch_execution_service=dispatch_execution_service,
        dispatch_registry=dispatch_registry,
        database_operations=database_operations,
        metrics=metrics_recorder,
        logger=app_logger,
    )

    dispatch_service = DispatchService(
        target_preparation_service=target_preparation_service,
        dispatch_execution_service=dispatch_execution_service,
        fallback_service=fallback_service,
        image_service=image_service,
        logger=app_logger,
    )

    admin_dashboard_service = build_admin_dashboard_service(
        usage=usage,
        chats=chats,
        metrics=metrics_recorder,
        image_client=image_client,
        text_client=text_client,
        models_repo=models_repo,
    )

    # Создаём ModelManagementService для управления моделями
    model_management_service = ModelManagementService(
        image_client=image_client,
        text_client=text_client,
        models_repo=models_repo,
        logger=app_logger,
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
        model_management_service=model_management_service,
    )


def build_bot(
    config: Config,
    db_pool: asyncpg.Pool,
    services: BotServices | None = None,
) -> WednesdayBot:
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
