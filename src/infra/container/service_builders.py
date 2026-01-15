"""Билдеры application‑сервисов (админка, БД‑операции, управление моделями, dispatch)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.admin_dashboard_service import AdminDashboardService
from app.admin_notification_service import AdminNotificationService
from app.api_status_service import APIStatusService
from app.database_operations_service import DatabaseOperationsService
from app.dispatch_delivery_service import DispatchDeliveryService
from app.dispatch_service import DispatchService
from app.fallback_image_delivery_service import FallbackImageDeliveryService
from app.frog_limit_service import FrogRateLimiterService
from app.image_service import ImageService
from app.model_management_service import ModelManagementService
from app.target_preparation_service import TargetPreparationService
from infra.repos.dispatch_registry import DispatchRegistry
from shared.config import AppSettings, Config
from shared.protocols.clients import ITextToImageClient, ITextToTextClient
from shared.protocols.dispatch import IDispatchRegistry
from shared.protocols.infrastructure import ILogger, IMetrics, IRateLimiter
from shared.protocols.messaging import IMessagingService
from shared.protocols.repositories import IAdminsRepo, IChatsRepo, IModelsRepo, IUsageTracker
from shared.protocols.uow import IUnitOfWorkFactory

if TYPE_CHECKING:
    pass


def build_api_status_service(
    *,
    config: Config,
    logger: ILogger,
    image_client: ITextToImageClient,
    text_client: ITextToTextClient | None,
    models_repo: IModelsRepo,
) -> APIStatusService:
    """Создаёт `APIStatusService` для проверки статуса внешних API."""
    api_logger = logger.bind(module="APIStatusService")
    return APIStatusService(
        image_client=image_client,
        text_client=text_client,
        models_store=models_repo,
        logger=api_logger,
    )


def build_admin_dashboard_service(  # noqa: PLR0913
    *,
    config: Config,
    logger: ILogger,
    usage: IUsageTracker,
    chats_repo: IChatsRepo,
    metrics: IMetrics,
    image_client: ITextToImageClient,
    text_client: ITextToTextClient | None,
    models_repo: IModelsRepo,
) -> AdminDashboardService:
    """Создаёт `AdminDashboardService`."""
    app_logger = logger.bind(module="AdminDashboardService")
    api_status_service = build_api_status_service(
        config=config,
        logger=logger,
        image_client=image_client,
        text_client=text_client,
        models_repo=models_repo,
    )

    return AdminDashboardService(
        usage=usage,
        chats=chats_repo,
        metrics=metrics,
        api_status_service=api_status_service,
        logger=app_logger,
    )


def build_frog_rate_limiter_service(
    *,
    app_settings: AppSettings,
    global_limiter: IRateLimiter,
    user_limiter: IRateLimiter,
    logger: ILogger,
    usage: IUsageTracker | None = None,
) -> FrogRateLimiterService:
    """Создаёт `FrogRateLimiterService` для ограничения частоты /frog."""
    rate_logger = logger.bind(module="FrogRateLimiterService")
    return FrogRateLimiterService(
        settings=app_settings,
        global_limiter=global_limiter,
        user_limiter=user_limiter,
        logger=rate_logger,
        usage=usage,
    )


def build_database_operations_service(
    *,
    logger: ILogger,
    usage: IUsageTracker,
    dispatch_registry: DispatchRegistry,
    metrics: IMetrics,
    uow_factory: IUnitOfWorkFactory,
) -> DatabaseOperationsService:
    """Создаёт `DatabaseOperationsService` для атомарных операций в БД."""
    db_logger = logger.bind(module="DatabaseOperationsService")
    return DatabaseOperationsService(
        dispatch_registry=dispatch_registry,
        usage_tracker=usage,
        metrics=metrics,
        unit_of_work_factory=uow_factory,
        logger=db_logger,
    )


def build_model_management_service(
    *,
    logger: ILogger,
    image_client: ITextToImageClient,
    text_client: ITextToTextClient | None,
    models_repo: IModelsRepo,
) -> ModelManagementService:
    """Создаёт `ModelManagementService` для управления моделями."""
    models_logger = logger.bind(module="ModelManagementService")
    return ModelManagementService(
        image_client=image_client,
        text_client=text_client,
        models_repo=models_repo,
        logger=models_logger,
    )


def build_fallback_image_delivery_service(
    *,
    image_service: ImageService,
    messaging_service: IMessagingService,
    logger: ILogger,
) -> FallbackImageDeliveryService:
    """Создаёт `FallbackImageDeliveryService` для доставки fallback изображений."""
    fallback_logger = logger.bind(module="FallbackImageDeliveryService")
    return FallbackImageDeliveryService(
        image_provider=image_service,
        messaging_service=messaging_service,
        logger=fallback_logger,
    )


def build_admin_notification_service(
    *,
    messaging_service: IMessagingService,
    admins_repo: IAdminsRepo,
    logger: ILogger,
) -> AdminNotificationService:
    """Создаёт `AdminNotificationService` для уведомления администраторов."""
    admin_notif_logger = logger.bind(module="AdminNotificationService")
    return AdminNotificationService(
        messaging_service=messaging_service,
        admins_repo=admins_repo,
        logger=admin_notif_logger,
    )


def build_target_preparation_service(
    *,
    chats_repo: IChatsRepo,
    dispatch_registry: IDispatchRegistry,
    messaging_service: IMessagingService,
    logger: ILogger,
) -> TargetPreparationService:
    """Создаёт `TargetPreparationService` для подготовки целей рассылки."""
    target_logger = logger.bind(module="TargetPreparationService")
    return TargetPreparationService(
        chats_repo=chats_repo,
        dispatch_registry=dispatch_registry,
        messaging_service=messaging_service,
        logger=target_logger,
    )


def build_dispatch_delivery_service(  # noqa: PLR0913
    *,
    dispatch_registry: IDispatchRegistry,
    database_operations: DatabaseOperationsService,
    messaging_service: IMessagingService,
    fallback_delivery: FallbackImageDeliveryService,
    metrics: IMetrics | None,
    logger: ILogger,
) -> DispatchDeliveryService:
    """Создаёт `DispatchDeliveryService` для доставки изображений в рассылках."""
    delivery_logger = logger.bind(module="DispatchDeliveryService")
    return DispatchDeliveryService(
        dispatch_registry=dispatch_registry,
        database_operations=database_operations,
        messaging_service=messaging_service,
        fallback_delivery=fallback_delivery,
        metrics=metrics,
        logger=delivery_logger,
    )


def build_dispatch_service(  # noqa: PLR0913
    *,
    target_preparation_service: TargetPreparationService,
    dispatch_delivery_service: DispatchDeliveryService,
    image_service: ImageService | None,
    admin_notifier: AdminNotificationService | None,
    metrics: IMetrics | None,
    settings: AppSettings,
    logger: ILogger,
) -> DispatchService:
    """Создаёт `DispatchService` для координации рассылки Wednesday Frog."""
    dispatch_logger = logger.bind(module="DispatchService")
    return DispatchService(
        target_preparation_service=target_preparation_service,
        dispatch_delivery_service=dispatch_delivery_service,
        image_service=image_service,
        admin_notifier=admin_notifier,
        metrics=metrics,
        settings=settings,
        logger=dispatch_logger,
    )
