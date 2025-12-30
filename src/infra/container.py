"""Composition root для сервисов бота.

Инкапсулирует сборку графа зависимостей backend‑части бота:
- формирует стек `ImageService` и связанные с ним доменные/инфраструктурные сервисы;
- создаёт контейнер `BotServices` для передачи зависимостей в хэндлеры и контроллеры;
- настраивает планировщик задач и вспомогательные application‑сервисы.
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import asyncpg

if TYPE_CHECKING:
    from app.admin_access_service import AdminAccessService
    from app.admin_command_service import AdminCommandService
    from bot.bot_error_handler import BotErrorHandler
    from bot.handlers.admin import AdminHandlers
    from bot.handlers.chat_event import ChatEventHandler
    from bot.handlers.models import ModelHandlers
    from bot.handlers.registry import BotHandlersRegistry
    from bot.handlers.user import UserHandlers
    from infra.redis.redis_client import RedisClient

from app.admin_dashboard_service import AdminDashboardService
from app.api_status_service import APIStatusService
from app.database_operations_service import DatabaseOperationsService
from app.dispatch_service import DispatchService
from app.frog_limit_service import FrogRateLimiterService
from app.image_existence_service import ImageExistenceService
from app.image_generation_coordinator import ImageGenerationCoordinator
from app.image_service import ImageService
from app.image_storage_coordinator import ImageStorageCoordinator
from app.image_storage_unit_of_work import ImageStorageUnitOfWork
from app.model_management_service import ModelManagementService
from app.prompt_service import PromptService
from domain.caption_service import CaptionService
from domain.image_generation import ImageGenerationService
from domain.prompt_generation import PromptGenerationService
from infra.cache.prompt_cache import PromptCache
from infra.cache.user_state_cache import UserStateCache
from infra.clients.client_manager import ClientManagementService
from infra.clients.image_client_container import get_image_client_container
from infra.clients.text_client_container import get_text_client_container
from infra.rate_limiting.circuit_breaker import CircuitBreakerService
from infra.rate_limiting.rate_limiter import RateLimiter
from infra.repos import AdminsRepo, ChatsRepo, ImagesRepo, ModelsRepo, PromptsRepo
from infra.repos.dispatch_registry import DispatchRegistry
from infra.repos.usage_tracker import UsageTracker
from infra.storage.failed_cache_queue import FailedCacheQueue
from infra.storage.image_storage import ImageStorageService
from shared.bot_services import BotServices
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
    IMetrics,
    IModelsRepo,
    IRateLimiter,
    ITaskQueue,
    ITextToImageClient,
    ITextToTextClient,
    IUnitOfWorkFactory,
    IUsageTracker,
)

if TYPE_CHECKING:
    import aiohttp
    from telegram import Bot
    from telegram.ext import Application

    from app.telegram_api_rate_limiter_service import TelegramAPIRateLimiterService


class Container:
    """Composition Root для сервисов бота.

    Инкапсулирует сборку графа зависимостей backend-части бота.
    Принимает уже созданные инфраструктурные ресурсы через протоколы,
    что обеспечивает loose coupling и упрощает тестирование.

    Принципы:
    - Контейнер не знает, как создавать пулы БД или Redis
    - Все инфраструктурные ресурсы создаются в main.py
    - Контейнер только собирает граф зависимостей из готовых компонентов
    """

    def __init__(
        self,
        config: Config,
        logger: ILogger,
        *,
        db_pool: asyncpg.Pool,
        redis_client: RedisClient,
        bot_client: Bot,
        metrics_service: IMetrics,
        task_queue: ITaskQueue,
        http_session: aiohttp.ClientSession,
    ) -> None:
        """Инициализирует контейнер с готовыми зависимостями.

        Args:
            config: Конфигурация приложения.
            logger: Логгер для использования в сервисах.
            db_pool: Пул подключений PostgreSQL (уже создан).
            redis_client: Redis-клиент (уже создан).
            bot_client: Telegram Bot клиент (уже создан).
            metrics_service: Сервис метрик (уже создан).
            task_queue: Очередь задач Celery (уже создана).
            http_session: Общая HTTP сессия для клиентов (уже создана).

        Raises:
            ValueError: Если обязательные параметры не переданы.
        """
        if config is None:
            raise ValueError("config не может быть None")
        if logger is None:
            raise ValueError("logger не может быть None")
        if db_pool is None:
            raise ValueError("db_pool не может быть None")
        if redis_client is None:
            raise ValueError("redis_client не может быть None")
        if bot_client is None:
            raise ValueError("bot_client не может быть None")
        if metrics_service is None:
            raise ValueError("metrics_service не может быть None")
        if task_queue is None:
            raise ValueError("task_queue не может быть None")
        if http_session is None:
            raise ValueError("http_session не может быть None")

        self._config = config
        self._logger = logger
        self._db_pool = db_pool
        self._redis_client = redis_client
        self._bot_client = bot_client
        self._metrics_service = metrics_service
        self._task_queue = task_queue
        self._http_session = http_session

        # Кэш для ленивого создания сервисов
        self._services: BotServices | None = None

    def _build_client_management_service(
        self,
        models_repo: IModelsRepo | None = None,
    ) -> ClientManagementService:
        """Создаёт ClientManagementService для управления ML-клиентами.

        Args:
            models_repo: Репозиторий моделей. Если None, используется self.models_repo.

        Returns:
            Экземпляр ClientManagementService.
        """
        if models_repo is None:
            models_repo = self.models_repo

        return ClientManagementService(
            models_repo=models_repo,
            logger=self._logger,
        )

    def _build_image_client(
        self,
        client_manager: ClientManagementService,
        models_repo: IModelsRepo,
    ) -> ITextToImageClient:
        """Создаёт и регистрирует клиент для генерации изображений.

        Args:
            client_manager: Сервис управления клиентами.
            models_repo: Репозиторий моделей.

        Returns:
            Контейнер с клиентом для генерации изображений.
        """
        logger = self._logger.bind(module="ImageClient")
        logger.debug(
            "Создание клиента для генерации изображений",
            event="container_create_image_client",
            status="started",
        )

        kandinsky_config = self._config.kandinsky
        image_client = client_manager.create_image_client(
            config=kandinsky_config,
            models_repo=models_repo,
            session=self._http_session,
            logger=self._logger,
        )

        # Регистрируем в контейнере
        image_container = get_image_client_container()
        image_container.set_initial_client(image_client)

        logger.debug(
            "Клиент для генерации изображений создан",
            event="container_image_client_created",
            status="ok",
        )
        return image_container

    def _build_text_client(
        self,
        client_manager: ClientManagementService,
        models_repo: IModelsRepo,
    ) -> ITextToTextClient | None:
        """Создаёт и регистрирует клиент для генерации текста (если настроен).

        Args:
            client_manager: Сервис управления клиентами.
            models_repo: Репозиторий моделей.

        Returns:
            Контейнер с клиентом для генерации текста или None, если не настроен.
        """
        logger = self._logger.bind(module="TextClient")
        gigachat_config = self._config.gigachat

        if not gigachat_config.authorization_key:
            logger.debug(
                "GigaChat не настроен, текстовый клиент не создан",
                event="container_text_client_skipped",
                status="ok",
            )
            return None

        logger.debug(
            "Создание клиента для генерации текста",
            event="container_create_text_client",
            status="started",
        )

        text_client = client_manager.create_text_client(
            config=gigachat_config,
            models_repo=models_repo,
            session=self._http_session,
            logger=self._logger,
        )

        if text_client is not None:
            text_container_instance = get_text_client_container()
            text_container_instance.set_initial_client(text_client)

            logger.debug(
                "Клиент для генерации текста создан",
                event="container_text_client_created",
                status="ok",
            )
            return text_container_instance

        logger.debug(
            "Не удалось создать клиент для генерации текста",
            event="container_text_client_failed",
            status="ok",
        )
        return None

    def _create_clients(
        self,
        models_repo: IModelsRepo | None = None,
    ) -> tuple[ITextToImageClient, ITextToTextClient | None]:
        """Создаёт клиенты для внешних ML‑сервисов через Dependency Injection.

        Клиенты создаются через ClientManagementService и регистрируются в контейнерах
        для поддержки runtime-замены и корректного cleanup.

        Args:
            models_repo: Репозиторий моделей для передачи в клиенты через DI.
                Если None, используется self.models_repo.

        Returns:
            Кортеж (image_client_container, text_client_container | None).
            Контейнеры реализуют интерфейсы ITextToImageClient и ITextToTextClient
            и обеспечивают runtime-замену клиентов.
        """
        if models_repo is None:
            models_repo = self.models_repo

        client_manager = self._build_client_management_service(models_repo=models_repo)
        image_client = self._build_image_client(client_manager, models_repo)
        text_client = self._build_text_client(client_manager, models_repo)

        return (image_client, text_client)

    def _build_image_generation_service(
        self,
        image_client: ITextToImageClient,
    ) -> ImageGenerationService:
        """Создаёт ImageGenerationService для генерации изображений.

        Args:
            image_client: Клиент для генерации изображений.

        Returns:
            Экземпляр ImageGenerationService.
        """
        return ImageGenerationService(image_client)

    def _build_prompt_generation_service(
        self,
        text_client: ITextToTextClient | None,
    ) -> PromptGenerationService:
        """Создаёт PromptGenerationService для генерации промптов.

        Args:
            text_client: Клиент для генерации текста.

        Returns:
            Экземпляр PromptGenerationService.
        """
        fallback_config = PromptFallbackConfig(
            frog_prompts=list(ImageConfig.FROG_PROMPTS),
            styles=list(ImageConfig.STYLES),
        )
        return PromptGenerationService(
            text_client=text_client,
            fallback_config=fallback_config,
        )

    def _build_image_storage_service(self) -> ImageStorageService:
        """Создаёт ImageStorageService для хранения изображений.

        Returns:
            Экземпляр ImageStorageService.
        """
        logger = self._logger.bind(module="ImageStorageService")
        return ImageStorageService(logger=logger)

    def _build_prompt_service(
        self,
        prompt_generation_service: PromptGenerationService,
        prompt_cache: PromptCache,
    ) -> PromptService:
        """Создаёт PromptService для работы с промптами.

        Args:
            prompt_generation_service: Сервис генерации промптов.
            prompt_cache: Кэш промптов.

        Returns:
            Экземпляр PromptService.
        """
        logger = self._logger.bind(module="PromptService")
        return PromptService(
            prompt_generation_service=prompt_generation_service,
            prompt_cache=prompt_cache,
            logger=logger,
        )

    def _build_caption_service(self) -> CaptionService | None:
        """Создаёт CaptionService из конфигурации (если настроен).

        Returns:
            Экземпляр CaptionService или None, если не настроен.
        """
        if ImageConfig.CAPTIONS:
            return CaptionService(ImageConfig.CAPTIONS)
        return None

    def _build_image_storage_uow(
        self,
        failed_cache_queue: FailedCacheQueue,
        image_existence_service: ImageExistenceService,
        image_storage: ImageStorageService,
    ) -> ImageStorageUnitOfWork:
        """Создаёт ImageStorageUnitOfWork для управления сохранением изображений.

        Args:
            failed_cache_queue: Очередь непересозданных записей.
            image_existence_service: Сервис проверки существования изображений.
            image_storage: Сервис хранения изображений.

        Returns:
            Экземпляр ImageStorageUnitOfWork.
        """
        logger = self._logger.bind(module="ImageStorageUnitOfWork")
        return ImageStorageUnitOfWork(
            failed_cache_queue=failed_cache_queue,
            image_existence_service=image_existence_service,
            storage=image_storage,
            logger=logger,
        )

    def _build_image_generation_coordinator(
        self,
        image_generation: ImageGenerationService,
        circuit_breaker: ICircuitBreaker,
        image_existence_service: ImageExistenceService,
    ) -> ImageGenerationCoordinator:
        """Создаёт ImageGenerationCoordinator для координации генерации изображений.

        Args:
            image_generation: Сервис генерации изображений.
            circuit_breaker: Circuit breaker для защиты от перегрузки.
            image_existence_service: Сервис проверки существования изображений.

        Returns:
            Экземпляр ImageGenerationCoordinator.
        """
        logger = self._logger.bind(module="ImageGenerationCoordinator")
        return ImageGenerationCoordinator(
            generation_service=image_generation,
            circuit_breaker=circuit_breaker,
            image_existence_service=image_existence_service,
            metrics=self._metrics_service,
            logger=logger,
        )

    def _build_image_storage_coordinator(
        self,
        image_storage_uow: ImageStorageUnitOfWork,
    ) -> ImageStorageCoordinator:
        """Создаёт ImageStorageCoordinator для координации хранения изображений.

        Args:
            image_storage_uow: Unit of Work для хранения изображений.

        Returns:
            Экземпляр ImageStorageCoordinator.
        """
        logger = self._logger.bind(module="ImageStorageCoordinator")
        return ImageStorageCoordinator(
            storage_unit_of_work=image_storage_uow,
            metrics=self._metrics_service,
            logger=logger,
        )

    def _build_image_stack(
        self,
        image_client: ITextToImageClient | None = None,
        text_client: ITextToTextClient | None = None,
        models_repo: IModelsRepo | None = None,
        prompt_cache: PromptCache | None = None,
    ) -> ImageService:
        """Собирает полный стек зависимостей для ImageService.

        Все клиенты, доменные и инфраструктурные сервисы создаются через приватные фабрики.

        Args:
            image_client: Опциональный клиент для генерации изображений.
                Если None, создаётся новый через DI в _create_clients().
            text_client: Опциональный клиент для генерации текста.
                Если None, создаётся новый через DI в _create_clients().
            models_repo: Репозиторий моделей для передачи в клиенты через DI.
                Если None, используется self.models_repo.
            prompt_cache: Кэш промптов для переиспользования. Если None, создаётся новый.

        Returns:
            Настроенный экземпляр ImageService.
        """
        # Инфраструктура и клиенты
        if image_client is None or text_client is None:
            created_image_client, created_text_client = self._create_clients(
                models_repo=models_repo,
            )
            if image_client is None:
                image_client = created_image_client
            if text_client is None:
                text_client = created_text_client

        # Используем переданный prompt_cache или создаём новый
        if prompt_cache is None:
            prompt_cache = PromptCache(redis_client=self._redis_client)

        # Используем контекстный логгер для ImageService
        app_logger = self._logger.bind(module="ImageService")

        # Доменные сервисы
        image_generation = self._build_image_generation_service(image_client)
        prompt_generation = self._build_prompt_generation_service(text_client)

        # Инфраструктура
        image_storage = self._build_image_storage_service()

        # Application‑сервисы
        prompt_service = self._build_prompt_service(
            prompt_generation_service=prompt_generation,
            prompt_cache=prompt_cache,
        )
        caption_service = self._build_caption_service()

        # Unit of Work и координаторы
        image_storage_uow = self._build_image_storage_uow(
            failed_cache_queue=self.failed_cache_queue,
            image_existence_service=self.image_existence_service,
            image_storage=image_storage,
        )
        generation_coordinator = self._build_image_generation_coordinator(
            image_generation=image_generation,
            circuit_breaker=self.circuit_breaker,
            image_existence_service=self.image_existence_service,
        )
        storage_coordinator = self._build_image_storage_coordinator(
            image_storage_uow=image_storage_uow,
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

    def _build_api_status_service(
        self,
        image_client: ITextToImageClient,
        text_client: ITextToTextClient | None,
        models_repo: IModelsRepo | None = None,
    ) -> APIStatusService:
        """Создаёт APIStatusService для инкапсуляции проверки статуса API.

        Args:
            image_client: Клиент для генерации изображений.
            text_client: Клиент для генерации текста.
            models_repo: Репозиторий моделей. Если None, используется self.models_repo.

        Returns:
            Экземпляр APIStatusService.
        """
        logger = self._logger.bind(module="APIStatusService")
        models_store = models_repo if models_repo is not None else self.models_repo

        return APIStatusService(
            image_client=image_client,
            text_client=text_client,
            models_store=models_store,
            logger=logger,
        )

    def _build_admin_dashboard_service(
        self,
        usage: IUsageTracker,
        image_client: ITextToImageClient,
        text_client: ITextToTextClient | None,
        models_repo: IModelsRepo | None = None,
    ) -> AdminDashboardService:
        """Собирает AdminDashboardService с зависимостями.

        Args:
            usage: Трекер использования для статистики.
            image_client: Клиент для генерации изображений.
            text_client: Клиент для генерации текста.
            models_repo: Репозиторий моделей для передачи в APIStatusService через DI.
                Если None, используется self.models_repo.

        Returns:
            Экземпляр AdminDashboardService с внедрёнными зависимостями.

        Raises:
            ValueError: Если обязательные параметры не переданы или имеют недопустимые значения.
        """
        # Валидация параметров
        if usage is None:
            raise ValueError("usage не может быть None")
        if image_client is None:
            raise ValueError("image_client не может быть None")

        # Используем контекстный логгер для AdminDashboardService
        app_logger = self._logger.bind(module="AdminDashboardService")

        # Создаём APIStatusService через приватную фабрику
        api_status_service = self._build_api_status_service(
            image_client=image_client,
            text_client=text_client,
            models_repo=models_repo,
        )

        return AdminDashboardService(
            usage=usage,
            chats=self.chats_repo,
            metrics=self._metrics_service,
            api_status_service=api_status_service,
            logger=app_logger,
        )

    def _build_admin_access_service(
        self,
        super_admin_id: int | None,
    ) -> AdminAccessService:
        """Создаёт AdminAccessService с зависимостями.

        Args:
            super_admin_id: ID главного администратора (из .env).

        Returns:
            Настроенный AdminAccessService.
        """
        from app.admin_access_service import AdminAccessService

        # Используем контекстный логгер для AdminAccessService
        logger = self._logger.bind(module="AdminAccessService")

        return AdminAccessService(
            admins_repo=self.admins_repo,
            super_admin_id=super_admin_id,
            logger=logger,
        )

    def _build_admin_command_service(
        self,
        usage: IUsageTracker,
        admin_access_service: AdminAccessService,
    ) -> AdminCommandService:
        """Создаёт AdminCommandService с зависимостями.

        Args:
            usage: Трекер использования.
            admin_access_service: Сервис проверки прав администратора.

        Returns:
            Настроенный AdminCommandService.
        """
        from app.admin_command_service import AdminCommandService

        # Используем контекстный логгер для AdminCommandService
        logger = self._logger.bind(module="AdminCommandService")

        return AdminCommandService(
            chats=self.chats_repo,
            usage=usage,
            admins_repo=self.admins_repo,
            admin_access_service=admin_access_service,
            logger=logger,
        )

    def _build_frog_rate_limiter(
        self,
    ) -> FrogRateLimiterService:
        """Создаёт FrogRateLimiterService для ограничения частоты запросов /frog.

        Returns:
            Экземпляр FrogRateLimiterService.
        """
        logger = self._logger.bind(module="FrogRateLimiterService")
        logger.debug(
            "Создание rate limiters для /frog",
            event="container_create_frog_rate_limiters",
            status="started",
        )

        frog_rate_limiter = FrogRateLimiterService(
            settings=self.app_settings,
            global_limiter=self.frog_global_rate_limiter,
            user_limiter=self.frog_user_rate_limiter,
            logger=logger,
        )

        logger.debug(
            "Frog rate limiters созданы",
            event="container_frog_rate_limiters_created",
            status="ok",
        )
        return frog_rate_limiter

    def _build_telegram_api_rate_limiter(
        self,
    ) -> TelegramAPIRateLimiterService:
        """Создаёт TelegramAPIRateLimiterService для ограничения частоты запросов к Telegram API.

        Returns:
            Экземпляр TelegramAPIRateLimiterService.
        """
        from app.telegram_api_rate_limiter_service import TelegramAPIRateLimiterService

        logger = self._logger.bind(module="TelegramAPIRateLimiterService")
        logger.debug(
            "Создание rate limiter для Telegram API",
            event="container_create_telegram_api_rate_limiter",
            status="started",
        )

        telegram_api_rate_limiter = TelegramAPIRateLimiterService(
            settings=self.app_settings,
            api_limiter=self.telegram_api_rate_limiter,
            logger=logger,
            max_parallel=self.app_settings.telegram_api_max_parallel_requests,
        )

        logger.debug(
            "Telegram API rate limiter создан",
            event="container_telegram_api_rate_limiter_created",
            status="ok",
        )
        return telegram_api_rate_limiter

    def _build_database_operations_service(
        self,
        usage: IUsageTracker,
        uow_factory: IUnitOfWorkFactory,
    ) -> DatabaseOperationsService:
        """Создаёт DatabaseOperationsService для атомарных операций БД.

        Args:
            usage: Трекер использования.
            uow_factory: Фабрика для создания Unit of Work.

        Returns:
            Экземпляр DatabaseOperationsService.
        """
        logger = self._logger.bind(module="DatabaseOperationsService")
        logger.debug(
            "Создание DatabaseOperationsService",
            event="container_create_database_operations",
            status="started",
        )

        database_operations = DatabaseOperationsService(
            dispatch_registry=self.dispatch_registry,
            usage_tracker=usage,
            metrics=self._metrics_service,
            unit_of_work_factory=uow_factory,
            logger=logger,
        )

        logger.debug(
            "DatabaseOperationsService создан",
            event="container_database_operations_created",
            status="ok",
        )
        return database_operations

    def _build_model_management_service(
        self,
        image_client: ITextToImageClient,
        text_client: ITextToTextClient | None,
    ) -> ModelManagementService:
        """Создаёт ModelManagementService для управления моделями.

        Args:
            image_client: Клиент для генерации изображений.
            text_client: Клиент для генерации текста.

        Returns:
            Экземпляр ModelManagementService.
        """
        logger = self._logger.bind(module="ModelManagementService")
        logger.debug(
            "Создание ModelManagementService",
            event="container_create_model_management",
            status="started",
        )

        model_management_service = ModelManagementService(
            image_client=image_client,
            text_client=text_client,
            models_repo=self.models_repo,
            logger=logger,
        )

        logger.debug(
            "ModelManagementService создан",
            event="container_model_management_created",
            status="ok",
        )
        return model_management_service

    @cached_property
    def models_repo(self) -> IModelsRepo:
        """Репозиторий моделей."""
        return ModelsRepo(pool=self._db_pool)

    @cached_property
    def chats_repo(self) -> IChatsRepo:
        """Репозиторий чатов."""
        return ChatsRepo(pool=self._db_pool)

    @cached_property
    def admins_repo(self) -> IAdminsRepo:
        """Репозиторий администраторов."""
        from shared.config import TelegramConfig

        telegram_config = TelegramConfig()
        return AdminsRepo(pool=self._db_pool, admin_chat_id=telegram_config.admin_chat_id)

    @cached_property
    def images_repo(self) -> ImagesRepo:
        """Репозиторий изображений."""
        return ImagesRepo(pool=self._db_pool)

    @cached_property
    def prompts_repo(self) -> PromptsRepo:
        """Репозиторий промптов."""
        return PromptsRepo(pool=self._db_pool)

    @cached_property
    def dispatch_registry(self) -> DispatchRegistry:
        """Реестр отправок."""
        return DispatchRegistry(pool=self._db_pool)

    @cached_property
    def prompt_cache(self) -> PromptCache:
        """Кэш промптов."""
        return PromptCache(redis_client=self._redis_client)

    @cached_property
    def app_settings(self) -> AppSettings:
        """Настройки приложения."""
        return AppSettings()

    @cached_property
    def circuit_breaker(self) -> ICircuitBreaker:
        """Circuit breaker для защиты Kandinsky API."""
        cb_config = self._config.circuit_breaker
        return CircuitBreakerService(
            redis_client=self._redis_client,
            key="cb:kandinsky_api",
            threshold=cb_config.threshold,
            window=cb_config.window,
            cooldown=cb_config.cooldown,
        )

    @cached_property
    def frog_global_rate_limiter(self) -> IRateLimiter:
        """Глобальный rate limiter для /frog команды."""
        return RateLimiter(
            redis_client=self._redis_client,
            prefix="frog:global:",
            window=self.app_settings.frog_rate_limit_window_seconds,
            limit=self.app_settings.frog_rate_limit_max_requests,
        )

    @cached_property
    def frog_user_rate_limiter(self) -> IRateLimiter:
        """Rate limiter для пользователей /frog команды."""
        SECONDS_PER_MINUTE = 60
        return RateLimiter(
            redis_client=self._redis_client,
            prefix="frog:user:",
            window=self.app_settings.frog_rate_limit_minutes * SECONDS_PER_MINUTE,
            limit=1,
        )

    @cached_property
    def telegram_api_rate_limiter(self) -> IRateLimiter:
        """Rate limiter для Telegram API."""
        from app.telegram_api_rate_limiter_service import (
            TELEGRAM_API_MAX_REQUESTS_PER_SECOND,
            TELEGRAM_API_WINDOW_SECONDS,
        )

        return RateLimiter(
            redis_client=self._redis_client,
            prefix="telegram_api:",
            window=TELEGRAM_API_WINDOW_SECONDS,
            limit=TELEGRAM_API_MAX_REQUESTS_PER_SECOND,
        )

    @cached_property
    def usage_tracker(self) -> UsageTracker:
        """UsageTracker для отслеживания использования."""
        return UsageTracker(
            pool=self._db_pool,
            monthly_quota=100,
            frog_threshold=70,
        )

    @cached_property
    def user_state_store(self) -> UserStateCache:
        """UserStateCache для хранения состояния пользователей."""
        return UserStateCache(redis_client=self._redis_client)

    @cached_property
    def uow_factory(self) -> IUnitOfWorkFactory:
        """Фабрика для Unit of Work."""
        from infra.database.database_unit_of_work import DatabaseUnitOfWork

        logger = self._logger.bind(module="UnitOfWorkFactory")

        def create_unit_of_work() -> DatabaseUnitOfWork:
            return DatabaseUnitOfWork(pool=self._db_pool, logger=logger)

        return create_unit_of_work

    @cached_property
    def image_existence_service(self) -> ImageExistenceService:
        """Сервис проверки существования изображений."""
        logger = self._logger.bind(module="ImageExistenceService")
        return ImageExistenceService(
            prompts_repo=self.prompts_repo,
            images_repo=self.images_repo,
            logger=logger,
        )

    @cached_property
    def failed_cache_queue(self) -> FailedCacheQueue:
        """Очередь непересозданных кэшей."""
        logger = self._logger.bind(module="FailedCacheQueue")
        return FailedCacheQueue(
            redis_client=self._redis_client,
            prefix="failed_cache:",
            logger=logger,
        )

    def build_bot_services(self) -> BotServices:
        """Собирает контейнер BotServices для основного бота.

        Использует приватные фабрики для создания всех сервисов.
        Реализует ленивое создание с кэшированием результата.

        Returns:
            Настроенный экземпляр BotServices (кэшируется после первого вызова).
        """
        # Ленивое создание с кэшированием
        if self._services is not None:
            self._logger.debug(
                "Использование кэшированного BotServices",
                event="container_use_cached_services",
                status="ok",
            )
            return self._services

        self._logger.debug(
            "Начало сборки BotServices",
            event="container_build_services_start",
            status="started",
        )

        # Создаём базовые компоненты
        image_client, text_client = self._create_clients()

        # Передаём prompt_cache из cached_property в _build_image_stack для переиспользования
        image_service = self._build_image_stack(
            image_client=image_client,
            text_client=text_client,
            prompt_cache=self.prompt_cache,
        )

        # Создаём сервисы через приватные фабрики
        frog_rate_limiter = self._build_frog_rate_limiter()
        telegram_api_rate_limiter = self._build_telegram_api_rate_limiter()
        database_operations = self._build_database_operations_service(
            self.usage_tracker,
            self.uow_factory,
        )
        model_management_service = self._build_model_management_service(
            image_client,
            text_client,
        )
        admin_dashboard_service = self._build_admin_dashboard_service(
            usage=self.usage_tracker,
            image_client=image_client,
            text_client=text_client,
        )

        # Создаём admin сервисы
        super_admin_id = None
        if self.app_settings.admin_chat_id:
            try:
                super_admin_id = int(self.app_settings.admin_chat_id)
            except (ValueError, TypeError):
                pass

        admin_access_service = self._build_admin_access_service(
            super_admin_id=super_admin_id,
        )
        admin_command_service = self._build_admin_command_service(
            usage=self.usage_tracker,
            admin_access_service=admin_access_service,
        )

        # Собираем финальный объект BotServices
        dispatch_service: DispatchService | None = None  # будет создан позже в bot слое

        services = BotServices(
            usage=self.usage_tracker,
            chats=self.chats_repo,
            dispatch_registry=self.dispatch_registry,
            metrics=self._metrics_service,
            prompt_cache=self.prompt_cache,
            user_state_store=self.user_state_store,
            settings=self.app_settings,
            image_service=image_service,
            frog_rate_limiter=frog_rate_limiter,
            task_queue=self._task_queue,
            bot_controller=None,
            dispatch_service=dispatch_service,
            admin_dashboard_service=admin_dashboard_service,
            model_management_service=model_management_service,
            admin_access_service=admin_access_service,
            admin_command_service=admin_command_service,
            messaging_service=None,  # будет установлен позже в bot слое
            database_operations=database_operations,
            admins_repo=self.admins_repo,
            telegram_api_rate_limiter=telegram_api_rate_limiter,
        )

        # Кэшируем результат
        self._services = services

        self._logger.info(
            "BotServices успешно собран и закэширован",
            event="container_build_services_success",
            status="ok",
        )
        return services

    def build_handlers_registry(self, application: Application) -> BotHandlersRegistry:
        """Собирает регистратор обработчиков для PTB Application.

        Скрывает внутри себя создание всех хендлеров (UserHandlers, AdminHandlers,
        ModelHandlers и прочих) и возвращает готовый объект BotHandlersRegistry.

        Args:
            application: PTB Application для регистрации обработчиков.

        Returns:
            Настроенный экземпляр BotHandlersRegistry.
        """
        self._logger.debug(
            "Начало сборки BotHandlersRegistry",
            event="container_build_handlers_start",
            status="started",
        )

        # 1. Сначала собираем общие сервисы (BotServices)
        services = self.build_bot_services()

        # 2. Создаем регистратор, вызывая внутренние фабрики хендлеров
        from bot.handlers.registry import BotHandlersRegistry

        self._logger.debug(
            "Создание хендлеров",
            event="container_create_handlers",
            status="started",
        )

        user_handlers = self._create_user_handlers(services)
        admin_handlers = self._create_admin_handlers(services)
        model_handlers = self._create_model_handlers(services)
        chat_event_handler = self._create_chat_event_handler(services, self._bot_client)
        error_handler = self._create_error_handler()

        self._logger.debug(
            "Все хендлеры созданы",
            event="container_handlers_created",
            status="ok",
        )

        registry = BotHandlersRegistry(
            application=application,
            user_handlers=user_handlers,
            admin_handlers=admin_handlers,
            model_handlers=model_handlers,
            chat_event_handler=chat_event_handler,
            error_handler=error_handler,
            logger=self._logger.bind(module="HandlersRegistry"),
        )

        self._logger.info(
            "BotHandlersRegistry успешно собран",
            event="container_build_handlers_success",
            status="ok",
        )

        return registry

    def _create_user_handlers(self, services: BotServices) -> UserHandlers:
        """Создает обработчики пользовательских команд."""
        from bot.handlers.user import UserHandlers

        self._logger.debug(
            "Создание UserHandlers",
            event="container_create_user_handlers",
            status="started",
        )
        handlers = UserHandlers(
            services=services,
            logger=self._logger.bind(module="UserHandlers"),
        )
        self._logger.debug(
            "UserHandlers создан",
            event="container_user_handlers_created",
            status="ok",
        )
        return handlers

    def _create_admin_handlers(self, services: BotServices) -> AdminHandlers:
        """Создает обработчики административных команд."""
        from bot.handlers.admin import AdminHandlers

        self._logger.debug(
            "Создание AdminHandlers",
            event="container_create_admin_handlers",
            status="started",
        )
        handlers = AdminHandlers(
            services=services,
            logger=self._logger.bind(module="AdminHandlers"),
        )
        self._logger.debug(
            "AdminHandlers создан",
            event="container_admin_handlers_created",
            status="ok",
        )
        return handlers

    def _create_model_handlers(self, services: BotServices) -> ModelHandlers:
        """Создает обработчики команд управления моделями."""
        from bot.handlers.models import ModelHandlers

        self._logger.debug(
            "Создание ModelHandlers",
            event="container_create_model_handlers",
            status="started",
        )
        handlers = ModelHandlers(
            services=services,
            logger=self._logger.bind(module="ModelHandlers"),
        )
        self._logger.debug(
            "ModelHandlers создан",
            event="container_model_handlers_created",
            status="ok",
        )
        return handlers

    def _create_chat_event_handler(
        self,
        services: BotServices,
        bot: Bot,
    ) -> ChatEventHandler:
        """Создает обработчик событий чата."""
        from bot.handlers.chat_event import ChatEventHandler

        self._logger.debug(
            "Создание ChatEventHandler",
            event="container_create_chat_event_handler",
            status="started",
        )
        handler = ChatEventHandler(
            services=services,
            bot=self._bot_client,
            logger=self._logger.bind(module="ChatEventHandler"),
        )
        self._logger.debug(
            "ChatEventHandler создан",
            event="container_chat_event_handler_created",
            status="ok",
        )
        return handler

    def _create_error_handler(self) -> BotErrorHandler:
        """Создает глобальный обработчик ошибок."""
        from bot.bot_error_handler import BotErrorHandler

        self._logger.debug(
            "Создание BotErrorHandler",
            event="container_create_error_handler",
            status="started",
        )
        handler = BotErrorHandler(
            logger=self._logger.bind(module="BotErrorHandler"),
        )
        self._logger.debug(
            "BotErrorHandler создан",
            event="container_error_handler_created",
            status="ok",
        )
        return handler
