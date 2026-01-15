"""Новый модульный DI‑контейнер для бота.

Этот класс координатора собирает граф зависимостей, делегируя создание
конкретных компонентов в специализированные модули:

- `repos` — репозитории и инфраструктура;
- `client_builders` — ML‑клиенты;
- `image_stack_builder` — стек `ImageService`;
- `rate_limiter_builders` — rate‑limiters и circuit breaker;
- `service_builders` — application‑сервисы;
- `admin_builders` — admin‑сервисы и Telegram API rate‑limiter;
- `handler_builders` — PTB‑хендлеры и реестр.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncpg

from bot.handlers.registry import BotHandlersRegistry
from infra.container.admin_builders import (
    build_admin_access_service,
    build_admin_command_service,
    build_telegram_api_rate_limiter_service,
)
from infra.container.client_builders import create_ml_clients
from infra.container.handler_builders import build_handlers_registry
from infra.container.image_stack_builder import build_image_stack
from infra.container.messaging_builders import build_ptb_messaging_service
from infra.container.rate_limiter_builders import (
    build_circuit_breaker,
    build_frog_global_rate_limiter,
    build_frog_user_rate_limiter,
    build_telegram_api_rate_limiter,
)
from infra.container.repos import ContainerRepos
from infra.container.service_builders import (
    build_admin_dashboard_service,
    build_admin_notification_service,
    build_database_operations_service,
    build_dispatch_delivery_service,
    build_dispatch_service,
    build_fallback_image_delivery_service,
    build_frog_rate_limiter_service,
    build_model_management_service,
    build_target_preparation_service,
)
from infra.redis.redis_client import RedisClient
from shared.bot_services import BotServices
from shared.config import AppSettings, Config
from shared.protocols.infrastructure import ILogger, IMetrics
from shared.protocols.queues import ITaskQueue

if TYPE_CHECKING:
    import aiohttp
    from telegram import Bot
    from telegram.ext import Application


class Container:
    """Composition Root для сервисов бота.

    Принимает уже созданные инфраструктурные ресурсы (БД, Redis, HTTP‑сессии),
    а затем собирает поверх них доменные и application‑сервисы.
    """

    def __init__(  # noqa: PLR0913
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

        self._repos = ContainerRepos(
            config=config,
            logger=logger,
            db_pool=db_pool,
            redis_client=redis_client,
        )

        self._services: BotServices | None = None

    # Удобные прокси к репозиториям/кэшам/настройкам

    @property
    def repos(self) -> ContainerRepos:
        """Доступ к репозиториям и инфраструктурным компонентам."""
        return self._repos

    def build_bot_services(self) -> BotServices:
        """Собирает контейнер `BotServices` для основного бота (лениво с кэшем)."""
        if self._services is not None:
            self._logger.debug(
                "Использование кэшированного BotServices",
                event="container_use_cached_services",
                status="ok",
            )
            return self._services

        log = self._logger
        log.debug(
            "Начало сборки BotServices",
            event="container_build_services_start",
            status="started",
        )

        # --- ML‑клиенты ---
        image_client, text_client = create_ml_clients(
            models_repo=self.repos.models_repo,
            config=self._config,
            http_session=self._http_session,
            logger=log,
        )

        # --- Rate‑limiters и circuit breaker ---
        app_settings: AppSettings = self.repos.app_settings
        circuit_breaker = build_circuit_breaker(
            config=self._config,
            redis_client=self._redis_client,
        )
        frog_global_limiter = build_frog_global_rate_limiter(
            app_settings=app_settings,
            redis_client=self._redis_client,
        )
        frog_user_limiter = build_frog_user_rate_limiter(
            app_settings=app_settings,
            redis_client=self._redis_client,
        )
        telegram_api_limiter = build_telegram_api_rate_limiter(
            redis_client=self._redis_client,
        )

        frog_rate_limiter_service = build_frog_rate_limiter_service(
            app_settings=app_settings,
            global_limiter=frog_global_limiter,
            user_limiter=frog_user_limiter,
            logger=log,
            usage=self.repos.usage_tracker,
        )

        # --- Messaging service ---
        messaging_service = build_ptb_messaging_service(bot=self._bot_client)

        # --- ImageService стек ---
        image_service = build_image_stack(
            image_client=image_client,
            text_client=text_client,
            prompt_cache=self.repos.prompt_cache,
            failed_cache_queue=self.repos.failed_cache_queue,
            prompts_repo=self.repos.prompts_repo,
            images_repo=self.repos.images_repo,
            circuit_breaker=circuit_breaker,
            metrics=self._metrics_service,
            logger=log,
        )

        # --- Application‑сервисы ---
        database_operations = build_database_operations_service(
            logger=log,
            usage=self.repos.usage_tracker,
            dispatch_registry=self.repos.dispatch_registry,
            metrics=self._metrics_service,
            uow_factory=self.repos.uow_factory,
        )
        model_management_service = build_model_management_service(
            logger=log,
            image_client=image_client,
            text_client=text_client,
            models_repo=self.repos.models_repo,
        )
        admin_dashboard_service = build_admin_dashboard_service(
            config=self._config,
            logger=log,
            usage=self.repos.usage_tracker,
            chats_repo=self.repos.chats_repo,
            metrics=self._metrics_service,
            image_client=image_client,
            text_client=text_client,
            models_repo=self.repos.models_repo,
            messaging_service=messaging_service,
        )

        # --- Admin‑сервисы ---
        super_admin_id: int | None = None
        if app_settings.admin_chat_id:
            try:
                super_admin_id = int(app_settings.admin_chat_id)
            except (TypeError, ValueError):
                super_admin_id = None

        admin_access_service = build_admin_access_service(
            admins_repo=self.repos.admins_repo,
            super_admin_id=super_admin_id,
            logger=log,
        )
        telegram_api_rate_limiter_service = build_telegram_api_rate_limiter_service(
            app_settings=app_settings,
            api_limiter=telegram_api_limiter,
            logger=log,
        )

        # --- Dispatch‑сервисы ---
        admin_notification_service = build_admin_notification_service(
            messaging_service=messaging_service,
            admins_repo=self.repos.admins_repo,
            logger=log,
        )
        fallback_image_delivery_service = build_fallback_image_delivery_service(
            image_service=image_service,
            messaging_service=messaging_service,
            logger=log,
        )
        target_preparation_service = build_target_preparation_service(
            chats_repo=self.repos.chats_repo,
            dispatch_registry=self.repos.dispatch_registry,
            messaging_service=messaging_service,
            logger=log,
        )
        dispatch_delivery_service = build_dispatch_delivery_service(
            dispatch_registry=self.repos.dispatch_registry,
            database_operations=database_operations,
            messaging_service=messaging_service,
            fallback_delivery=fallback_image_delivery_service,
            metrics=self._metrics_service,
            logger=log,
        )
        dispatch_service = build_dispatch_service(
            target_preparation_service=target_preparation_service,
            dispatch_delivery_service=dispatch_delivery_service,
            image_service=image_service,
            admin_notifier=admin_notification_service,
            metrics=self._metrics_service,
            settings=app_settings,
            logger=log,
        )

        # Создаем chat_info_service и admin_command_service после dispatch_delivery_service
        from app.chat_info_service import ChatInfoService

        chat_info_service = ChatInfoService(
            messaging_service=messaging_service,
            logger=log,
        )

        admin_command_service = build_admin_command_service(
            chats_repo=self.repos.chats_repo,
            usage=self.repos.usage_tracker,
            admins_repo=self.repos.admins_repo,
            admin_access_service=admin_access_service,
            logger=log,
            image_service=image_service,
            frog_limit_service=frog_rate_limiter_service,
            dispatch_delivery_service=dispatch_delivery_service,
            chat_info_service=chat_info_service,
        )

        from app.chat_event_service import ChatEventService
        from app.help_message_service import HelpMessageService
        from app.user_extraction_service import UserExtractionService

        chat_event_service = ChatEventService(
            admin_command_service=admin_command_service,
            chat_info_service=chat_info_service,
            messaging_service=messaging_service,
            logger=log,
        )

        user_extraction_service = UserExtractionService(
            logger=log,
        )

        help_message_service = HelpMessageService(
            logger=log,
        )

        from app.bot_notification_builders import BotNotificationBuilders
        from app.command_error_handler_service import CommandErrorHandlerService
        from app.command_validation_service import CommandValidationService
        from app.error_classification_service import ErrorClassificationService
        from app.error_message_formatter_service import ErrorMessageFormatterService
        from app.error_reporting_service import ErrorReportingService
        from app.frog_command_service import FrogCommandService
        from app.retry_strategy_service import RetryStrategyService

        bot_notification_builders = BotNotificationBuilders()

        error_formatter = ErrorMessageFormatterService(
            logger=log,
        )

        retry_strategy = RetryStrategyService(
            logger=log,
        )

        command_error_handler = CommandErrorHandlerService(
            error_formatter=error_formatter,
            retry_strategy=retry_strategy,
            logger=log,
        )

        command_validation_service = CommandValidationService(
            logger=log,
        )

        error_classification_service = ErrorClassificationService(
            logger=log,
        )

        error_reporting_service = ErrorReportingService(
            error_classification_service=error_classification_service,
            logger=log,
        )

        frog_command_service = FrogCommandService(
            frog_rate_limiter=frog_rate_limiter_service,
            admin_access_service=admin_access_service,
            task_queue=self._task_queue,
            notification_builders=bot_notification_builders,
            logger=log,
        )

        services = BotServices(
            usage=self.repos.usage_tracker,
            chats=self.repos.chats_repo,
            dispatch_registry=self.repos.dispatch_registry,
            metrics=self._metrics_service,
            prompt_cache=self.repos.prompt_cache,
            user_state_store=self.repos.user_state_store,
            settings=app_settings,
            image_service=image_service,
            frog_rate_limiter=frog_rate_limiter_service,
            task_queue=self._task_queue,
            dispatch_service=dispatch_service,
            admin_dashboard_service=admin_dashboard_service,
            model_management_service=model_management_service,
            admin_access_service=admin_access_service,
            admin_command_service=admin_command_service,
            admin_notification_service=admin_notification_service,
            chat_info_service=chat_info_service,
            command_error_handler=command_error_handler,
            messaging_service=messaging_service,
            database_operations=database_operations,
            admins_repo=self.repos.admins_repo,
            telegram_api_rate_limiter=telegram_api_rate_limiter_service,
            user_extraction_service=user_extraction_service,
            help_message_service=help_message_service,
            chat_event_service=chat_event_service,
            bot_notification_builders=bot_notification_builders,
            frog_command_service=frog_command_service,
            error_formatter=error_formatter,
            retry_strategy=retry_strategy,
            command_validation_service=command_validation_service,
            error_classification_service=error_classification_service,
            error_reporting_service=error_reporting_service,
        )

        self._services = services

        log.info(
            "BotServices успешно собран и закэширован",
            event="container_build_services_success",
            status="ok",
        )
        return services

    def build_handlers_registry(self, application: Application) -> BotHandlersRegistry:
        """Собирает `BotHandlersRegistry` и все обработчики для PTB `Application`."""
        services = self.build_bot_services()
        return build_handlers_registry(
            application=application,
            services=services,
            bot=self._bot_client,
            logger=self._logger,
        )
