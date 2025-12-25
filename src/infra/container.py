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
    from app.admin_access_service import AdminAccessService
    from app.admin_command_service import AdminCommandService
    from app.admin_notification_service import AdminNotificationService
    from app.frog_processing_service import FrogProcessingService
    from bot.wednesday_bot import WednesdayBot
    from infra.cleanup_service import CleanupService
    from infra.redis.redis_client import RedisClient

from app.admin_dashboard_service import AdminDashboardService
from app.api_status_service import APIStatusService
from app.database_operations_service import DatabaseOperationsService
from app.dispatch_delivery_service import DispatchDeliveryService
from app.dispatch_service import DispatchService
from app.frog_limit_service import FrogRateLimiterService
from app.image_generation_coordinator import ImageGenerationCoordinator
from app.image_service import ImageService
from app.image_storage_coordinator import ImageStorageCoordinator
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
from infra.rate_limiting.circuit_breaker import CircuitBreakerService
from infra.rate_limiting.rate_limiter import RateLimiter
from infra.repos import AdminsRepo, ChatsRepo, ImagesRepo, ModelsRepo, PromptsRepo
from infra.repos.dispatch_registry import DispatchRegistry
from infra.repos.usage_tracker import UsageTracker
from infra.storage.failed_cache_queue import FailedCacheQueue
from infra.storage.image_storage import ImageStorageService
from shared.bot_services import BotServices, SupportBotServices
from shared.config import (
    AppSettings,
    Config,
    ImageConfig,
    PromptFallbackConfig,
)
from shared.protocols import (
    IAdminsRepo,
    IChatsRepo,
    ICircuitBreaker,
    ILogger,
    IMessagingService,
    IMetrics,
    IModelsRepo,
    IRateLimiter,
    ITextToImageClient,
    ITextToTextClient,
    IUnitOfWorkFactory,
    IUsageTracker,
)


def _create_clients(
    config: Config,
    db_pool: asyncpg.Pool,
    models_repo: IModelsRepo | None = None,
) -> tuple[ITextToImageClient, ITextToTextClient | None]:
    """Создаёт клиенты для внешних ML‑сервисов через Dependency Injection.

    Клиенты создаются через ClientManagementService и регистрируются в контейнерах
    для поддержки runtime-замены и корректного cleanup.

    Args:
        config: Экземпляр Config для создания конфигураций клиентов.
        db_pool: Пул подключений PostgreSQL (обязательный параметр).
        models_repo: Репозиторий моделей для передачи в клиенты через DI.
            Если None, создаётся новый ModelsRepo с переданным пулом.

    Returns:
        Кортеж (image_client_container, text_client_container | None).
        Контейнеры реализуют интерфейсы ITextToImageClient и ITextToTextClient
        и обеспечивают runtime-замену клиентов.
    """
    # Создаём models_repo, если не передан
    if models_repo is None:
        from infra.repos import ModelsRepo

        models_repo = ModelsRepo(pool=db_pool)

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


def build_image_stack(  # noqa: PLR0913, PLR0917
    config: Config,
    db_pool: asyncpg.Pool,
    redis_client: RedisClient,
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
        redis_client: Redis-клиент для использования в сервисах.
        image_client: Опциональный клиент для генерации изображений.
            Если None, создаётся новый через DI в _create_clients().
        text_client: Опциональный клиент для генерации текста.
            Если None, создаётся новый через DI в _create_clients().
        models_repo: Репозиторий моделей для передачи в клиенты через DI.

    Returns:
        Настроенный экземпляр ImageService.

    Raises:
        ValueError: Если обязательные параметры не переданы или имеют недопустимые значения.
    """
    # Валидация параметров
    if config is None:
        raise ValueError("config не может быть None")
    if db_pool is None:
        raise ValueError("db_pool не может быть None")
    if redis_client is None:
        raise ValueError("redis_client не может быть None")

    # Инфраструктура и клиенты
    if image_client is None or text_client is None:
        # Используем _create_clients() вместо дублирования логики
        created_image_client, created_text_client = _create_clients(
            config,
            db_pool=db_pool,
            models_repo=models_repo,
        )
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

    # Создаём очередь для непересозданных кэшей
    failed_cache_queue = FailedCacheQueue(
        redis_client=redis_client,
        prefix="failed_cache:",
        logger=app_logger,
    )

    # Получаем конфигурацию circuit breaker
    cb_config = config.circuit_breaker
    circuit_breaker: ICircuitBreaker = CircuitBreakerService(
        redis_client=redis_client,
        key="cb:kandinsky_api",
        threshold=cb_config.threshold,
        window=cb_config.window,
        cooldown=cb_config.cooldown,
    )
    # Создаём Metrics для передачи в ImageService
    metrics = Metrics(pool=db_pool, logger=app_logger)

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
        failed_cache_queue=failed_cache_queue,
        cache=image_cache,
        storage=image_storage,
        logger=app_logger,
    )

    # Создаём координаторы
    generation_coordinator = ImageGenerationCoordinator(
        generation_service=image_generation,
        circuit_breaker=circuit_breaker,
        image_cache=image_cache,
        metrics=metrics,
        logger=app_logger,
    )

    storage_coordinator = ImageStorageCoordinator(
        storage_unit_of_work=image_storage_uow,
        metrics=metrics,
        logger=app_logger,
    )

    # Создаём главный сервис
    return ImageService(
        prompt_service=prompt_service,
        generation_coordinator=generation_coordinator,
        storage_coordinator=storage_coordinator,
        image_storage=image_storage,
        caption_service=caption_service,
        logger=app_logger,
    )


def build_admin_dashboard_service(  # noqa: PLR0913, PLR0917
    usage: IUsageTracker,
    chats: IChatsRepo,
    metrics: IMetrics,
    image_client: ITextToImageClient,
    text_client: ITextToTextClient | None,
    db_pool: asyncpg.Pool,
    models_repo: IModelsRepo | None = None,
) -> AdminDashboardService:
    """Собирает AdminDashboardService с зависимостями.

    Args:
        usage: Трекер использования для статистики.
        chats: Хранилище чатов для получения списка активных чатов.
        metrics: Метрики производительности.
        image_client: Клиент для генерации изображений.
        text_client: Клиент для генерации текста.
        db_pool: Пул подключений PostgreSQL (обязательный параметр).
        models_repo: Репозиторий моделей для передачи в APIStatusService через DI.

    Returns:
        Экземпляр AdminDashboardService с внедрёнными зависимостями.

    Raises:
        ValueError: Если обязательные параметры не переданы или имеют недопустимые значения.
    """
    # Валидация параметров
    if usage is None:
        raise ValueError("usage не может быть None")
    if chats is None:
        raise ValueError("chats не может быть None")
    if metrics is None:
        raise ValueError("metrics не может быть None")
    if image_client is None:
        raise ValueError("image_client не может быть None")
    if db_pool is None:
        raise ValueError("db_pool не может быть None")

    models_store = models_repo if models_repo is not None else ModelsRepo(pool=db_pool)

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


def build_admin_access_service(
    admins_repo: IAdminsRepo,
    super_admin_id: int | None,
    logger: ILogger,
) -> AdminAccessService:
    """Создаёт AdminAccessService с зависимостями.

    Args:
        admins_repo: Репозиторий администраторов.
        super_admin_id: ID главного администратора (из .env).
        logger: Логгер.

    Returns:
        Настроенный AdminAccessService.
    """
    from app.admin_access_service import AdminAccessService

    return AdminAccessService(
        admins_repo=admins_repo,
        super_admin_id=super_admin_id,
        logger=logger,
    )


def build_admin_notification_service(
    messaging_service: IMessagingService,
    admins_repo: IAdminsRepo,
    logger: ILogger,
) -> AdminNotificationService:
    """Создаёт AdminNotificationService с зависимостями.

    Args:
        messaging_service: Сервис отправки сообщений.
        admins_repo: Репозиторий администраторов.
        logger: Логгер.

    Returns:
        Настроенный AdminNotificationService.
    """
    from app.admin_notification_builders import (
        DispatchErrorNotificationBuilder,
        GenerationErrorNotificationBuilder,
    )
    from app.admin_notification_service import AdminNotificationService

    generation_builder = GenerationErrorNotificationBuilder()
    dispatch_builder = DispatchErrorNotificationBuilder()

    return AdminNotificationService(
        messaging_service=messaging_service,
        admins_repo=admins_repo,
        generation_builder=generation_builder,
        dispatch_builder=dispatch_builder,
        logger=logger,
    )


def build_admin_command_service(
    chats: IChatsRepo | None,
    usage: IUsageTracker | None,
    admins_repo: IAdminsRepo,
    admin_access_service: AdminAccessService,
    logger: ILogger,
) -> AdminCommandService:
    """Создаёт AdminCommandService с зависимостями.

    Args:
        chats: Репозиторий чатов (опционально).
        usage: Трекер использования (опционально).
        admins_repo: Репозиторий администраторов.
        admin_access_service: Сервис проверки прав администратора.
        logger: Логгер.

    Returns:
        Настроенный AdminCommandService.
    """
    from app.admin_command_service import AdminCommandService

    return AdminCommandService(
        chats=chats,
        usage=usage,
        admins_repo=admins_repo,
        admin_access_service=admin_access_service,
        logger=logger,
    )


def build_frog_processing_service(
    image_service: ImageService,
    messaging_service: IMessagingService,
    usage_tracker: IUsageTracker | None,
    admin_notifier: AdminNotificationService | None,
    logger: ILogger,
) -> FrogProcessingService:
    """Создаёт FrogProcessingService с зависимостями.

    Args:
        image_service: Сервис генерации изображений.
        messaging_service: Сервис отправки сообщений.
        usage_tracker: Трекер использования.
        admin_notifier: Сервис уведомления администраторов.
        logger: Логгер.

    Returns:
        Настроенный FrogProcessingService.
    """
    from app.fallback_image_delivery_service import FallbackImageDeliveryService
    from app.frog_delivery_service import FrogDeliveryService
    from app.frog_processing_service import FrogProcessingService

    # Создаём FallbackImageDeliveryService для переиспользования логики fallback
    fallback_delivery = FallbackImageDeliveryService(
        image_provider=image_service,
        messaging_service=messaging_service,
        logger=logger,
    )

    delivery_service = FrogDeliveryService(
        fallback_delivery=fallback_delivery,
        messaging_service=messaging_service,
        logger=logger,
    )

    return FrogProcessingService(
        image_service=image_service,
        delivery_service=delivery_service,
        usage_tracker=usage_tracker,
        admin_notifier=admin_notifier,
        logger=logger,
    )


def build_cleanup_service(logger: ILogger) -> CleanupService:
    """Создаёт CleanupService с зависимостями.

    Args:
        logger: Логгер.

    Returns:
        Настроенный CleanupService.
    """
    from infra.cleanup_service import CleanupService

    return CleanupService(logger=logger)


def build_support_bot_services(
    db_pool: asyncpg.Pool,
    redis_client: RedisClient,
) -> SupportBotServices:
    """Собирает минимальный контейнер SupportBotServices для резервного бота.

    Создает только необходимые зависимости для SupportBot:
    - admins_repo для проверки прав администратора
    - chats для обработки событий чата
    - settings для конфигурации

    Cleanup ресурсов выполняется через глобальные функции close_postgres_pool()
    и close_redis(), поэтому инфраструктурные объекты не хранятся в контейнере.

    Args:
        db_pool: Пул подключений PostgreSQL.
        redis_client: Redis-клиент для использования в сервисах.

    Returns:
        Настроенный экземпляр SupportBotServices.

    Raises:
        ValueError: Если обязательные параметры не переданы или имеют недопустимые значения.
    """
    from shared.bot_services import SupportBotServices
    from shared.config import AppSettings, TelegramConfig

    # Валидация параметров
    if db_pool is None:
        raise ValueError("db_pool не может быть None")
    if redis_client is None:
        raise ValueError("redis_client не может быть None")

    # Создаём AppSettings из Config
    app_settings = AppSettings()

    # Создаём AdminsRepo для admin сервисов
    # Используем исходное значение из TelegramConfig (str), а не из AppSettings (int)
    telegram_config = TelegramConfig()
    admins_repo = AdminsRepo(pool=db_pool, admin_chat_id=telegram_config.admin_chat_id)

    # Создаём ChatsRepo для обработки событий чата
    chats = ChatsRepo(pool=db_pool)

    return SupportBotServices(
        admins_repo=admins_repo,
        chats=chats,
        settings=app_settings,
    )


def build_bot_services(config: Config, db_pool: asyncpg.Pool, redis_client: RedisClient) -> BotServices:
    """Собирает контейнер BotServices для основного бота.

    На этом этапе:
    - image_service создаётся через build_image_stack();
    - остальные сервисы повторяют существующую инициализацию из WednesdayBot.

    Args:
        config: Экземпляр Config для создания сервисов и настроек.
        db_pool: Пул подключений PostgreSQL.
        redis_client: Redis-клиент для использования в сервисах.

    Returns:
        Настроенный экземпляр BotServices.

    Raises:
        ValueError: Если обязательные параметры не переданы или имеют недопустимые значения.
    """
    # Валидация параметров
    if config is None:
        raise ValueError("config не может быть None")
    if db_pool is None:
        raise ValueError("db_pool не может быть None")
    if redis_client is None:
        raise ValueError("redis_client не может быть None")

    # Создаём AppSettings из Config
    from shared.config import AppSettings

    app_settings = AppSettings()

    # Создаём общий логгер для всех сервисов
    app_logger = get_logger("app")

    # Создаём ModelsRepo один раз для переиспользования во всех сервисах
    models_repo = ModelsRepo(pool=db_pool)

    # Создаём клиенты один раз для переиспользования во всех сервисах
    image_client, text_client = _create_clients(
        config,
        db_pool=db_pool,
        models_repo=models_repo,
    )

    # Создаём image_service с переиспользованием клиентов
    image_service = build_image_stack(
        config=config,
        image_client=image_client,
        text_client=text_client,
        models_repo=models_repo,
        db_pool=db_pool,
        redis_client=redis_client,
    )

    usage = UsageTracker(
        pool=db_pool,
        monthly_quota=100,
        frog_threshold=70,
    )

    chats = ChatsRepo(pool=db_pool)
    dispatch_registry = DispatchRegistry(pool=db_pool)
    # Создаём Metrics
    metrics = Metrics(pool=db_pool, logger=app_logger)

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
    from infra.celery.celery_task_queue import CeleryTaskQueue

    # Создаём task queue для прямого использования в handlers
    task_queue = CeleryTaskQueue()

    # Создаём фабрику для Unit of Work
    from infra.database.database_unit_of_work import DatabaseUnitOfWork

    def create_unit_of_work() -> DatabaseUnitOfWork:
        return DatabaseUnitOfWork(pool=db_pool, logger=app_logger)

    # Аннотируем для явности соответствия протоколу
    uow_factory: IUnitOfWorkFactory = create_unit_of_work

    # Создаём DatabaseOperationsService для атомарных операций БД
    database_operations = DatabaseOperationsService(
        dispatch_registry=dispatch_registry,
        usage_tracker=usage,
        metrics=metrics,
        unit_of_work_factory=uow_factory,
        logger=app_logger,
    )

    # Dispatch сервисы будут созданы позже в bot слое, когда будет доступен messaging_service
    dispatch_service: DispatchService | None = None

    admin_dashboard_service = build_admin_dashboard_service(
        usage=usage,
        chats=chats,
        metrics=metrics,
        image_client=image_client,
        text_client=text_client,
        db_pool=db_pool,
        models_repo=models_repo,
    )

    # Создаём ModelManagementService для управления моделями
    model_management_service = ModelManagementService(
        image_client=image_client,
        text_client=text_client,
        models_repo=models_repo,
        logger=app_logger,
    )

    # Создаём AdminsRepo для admin сервисов
    # Используем исходное значение из TelegramConfig (str), а не из AppSettings (int)
    from shared.config import TelegramConfig

    telegram_config = TelegramConfig()
    admins_repo = AdminsRepo(pool=db_pool, admin_chat_id=telegram_config.admin_chat_id)

    # Создаём AdminAccessService
    super_admin_id = None
    if app_settings.admin_chat_id:
        try:
            super_admin_id = int(app_settings.admin_chat_id)
        except (ValueError, TypeError):
            pass

    admin_access_service = build_admin_access_service(
        admins_repo=admins_repo,
        super_admin_id=super_admin_id,
        logger=app_logger,
    )

    # Создаём AdminCommandService
    admin_command_service = build_admin_command_service(
        chats=chats,
        usage=usage,
        admins_repo=admins_repo,
        admin_access_service=admin_access_service,
        logger=app_logger,
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
        task_queue=task_queue,
        bot_controller=None,
        dispatch_service=dispatch_service,
        admin_dashboard_service=admin_dashboard_service,
        model_management_service=model_management_service,
        admin_access_service=admin_access_service,
        admin_command_service=admin_command_service,
        messaging_service=None,  # будет установлен позже в bot слое
        database_operations=database_operations,
        admins_repo=admins_repo,
    )


def build_dispatch_services(  # noqa: PLR0913, PLR0917
    messaging_service: IMessagingService,
    chats: IChatsRepo,
    dispatch_registry: DispatchRegistry,
    database_operations: DatabaseOperationsService,
    image_service: ImageService,
    metrics: IMetrics,
    admins_repo: IAdminsRepo,
    logger: ILogger,
    settings: AppSettings | None = None,
) -> tuple[TargetPreparationService, DispatchDeliveryService, DispatchService, AdminNotificationService]:
    """Создаёт dispatch сервисы с messaging_service.

    Args:
        messaging_service: Сервис отправки сообщений.
        chats: Репозиторий чатов.
        dispatch_registry: Реестр отправок.
        database_operations: Сервис операций БД.
        image_service: Сервис генерации изображений.
        metrics: Сервис метрик.
        admins_repo: Репозиторий администраторов.
        logger: Логгер.
        settings: Настройки приложения для определения временных слотов (опционально).

    Returns:
        Кортеж (target_preparation_service, dispatch_delivery_service, dispatch_service, admin_notification_service).
    """
    target_preparation_service = TargetPreparationService(
        chats_repo=chats,
        dispatch_registry=dispatch_registry,
        messaging_service=messaging_service,
        logger=logger,
    )

    # Создаём FallbackImageDeliveryService для переиспользования логики fallback
    from app.fallback_image_delivery_service import FallbackImageDeliveryService

    fallback_delivery = FallbackImageDeliveryService(
        image_provider=image_service,
        messaging_service=messaging_service,
        logger=logger,
    )

    dispatch_delivery_service = DispatchDeliveryService(
        dispatch_registry=dispatch_registry,
        database_operations=database_operations,
        messaging_service=messaging_service,
        fallback_delivery=fallback_delivery,
        metrics=metrics,
        logger=logger,
    )

    admin_notifier = build_admin_notification_service(
        messaging_service=messaging_service,
        admins_repo=admins_repo,
        logger=logger,
    )

    dispatch_service = DispatchService(
        target_preparation_service=target_preparation_service,
        dispatch_delivery_service=dispatch_delivery_service,
        image_service=image_service,
        admin_notifier=admin_notifier,
        metrics=metrics,
        settings=settings,
        logger=logger,
    )

    return target_preparation_service, dispatch_delivery_service, dispatch_service, admin_notifier


def build_bot(
    config: Config,
    db_pool: asyncpg.Pool,
    redis_client: RedisClient,
    services: BotServices | None = None,
) -> WednesdayBot:
    """Создаёт и настраивает экземпляр WednesdayBot.

    Единственная точка создания WednesdayBot в приложении. Использует
    Dependency Injection для передачи зависимостей в бот.

    Args:
        config: Экземпляр Config для создания сервисов и зависимостей.
        db_pool: Пул подключений PostgreSQL.
        redis_client: Redis-клиент для использования в сервисах.
        services: Опциональный контейнер сервисов. Если None, создаётся
            новый через build_bot_services().

    Returns:
        Настроенный экземпляр WednesdayBot с внедрёнными зависимостями.

    Raises:
        ValueError: Если обязательные параметры не переданы или имеют недопустимые значения.

    Note:
        Эта функция является Composition Root для WednesdayBot. Все зависимости
        создаются здесь и передаются в бот через конструктор.
    """
    # Валидация параметров
    if config is None:
        raise ValueError("config не может быть None")
    if db_pool is None:
        raise ValueError("db_pool не может быть None")
    if redis_client is None:
        raise ValueError("redis_client не может быть None")

    # Ленивый импорт для избежания циклических зависимостей
    from bot.wednesday_bot import WednesdayBot
    from shared.config import BotTelegramConfig

    if services is None:
        services = build_bot_services(config, db_pool, redis_client)

    # Извлекаем только необходимые поля для bot-слоя (соблюдение границ слоёв)
    bot_telegram_config = BotTelegramConfig(
        bot_token=config.telegram.bot_token or "",
        chat_id=config.telegram.chat_id,
    )

    # Создаём логгер для bot-слоя
    bot_logger = get_logger("bot.wednesday_bot")

    # Создаём бот с внедрёнными зависимостями
    bot = WednesdayBot(services=services, telegram_config=bot_telegram_config, logger=bot_logger)

    # Устанавливаем обратную ссылку в composition root для избежания циклической зависимости
    # bot_controller должен быть установлен здесь, а не в конструкторе WednesdayBot
    services.bot_controller = bot

    # Создаём messaging_service после создания бота, так как нужен bot.application.bot
    from infra.messaging.ptb import PTBMessagingService

    messaging_service = PTBMessagingService(bot=bot.application.bot)
    services.messaging_service = messaging_service

    # Создаём chat_info_service после создания бота, так как нужен bot.application.bot
    from app.chat_info_service import ChatInfoService

    app_logger = get_logger("app")
    chat_info_service = ChatInfoService(bot=bot.application.bot, logger=app_logger)
    services.chat_info_service = chat_info_service

    # Создаём dispatch сервисы с messaging_service
    if services.database_operations is not None and services.admins_repo is not None:
        app_logger = get_logger("app")
        _target_prep, _dispatch_delivery, dispatch, admin_notifier = build_dispatch_services(
            messaging_service=messaging_service,
            chats=services.chats,
            dispatch_registry=services.dispatch_registry,
            database_operations=services.database_operations,
            image_service=services.image_service,
            metrics=services.metrics,
            admins_repo=services.admins_repo,
            logger=app_logger,
            settings=services.settings,
        )
        # Обновляем services
        services.dispatch_service = dispatch
        services.admin_notification_service = admin_notifier
    else:
        app_logger = get_logger("app")
        app_logger.warning(
            "database_operations или admins_repo не доступны, dispatch_service не будет создан",
        )

    return bot
