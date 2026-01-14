"""Билдеры application‑сервисов (админка, БД‑операции, управление моделями)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.admin_dashboard_service import AdminDashboardService
from app.api_status_service import APIStatusService
from app.database_operations_service import DatabaseOperationsService
from app.frog_limit_service import FrogRateLimiterService
from app.model_management_service import ModelManagementService
from infra.repos.dispatch_registry import DispatchRegistry
from shared.config import AppSettings, Config
from shared.protocols.clients import ITextToImageClient, ITextToTextClient
from shared.protocols.infrastructure import ILogger, IMetrics, IRateLimiter
from shared.protocols.repositories import IChatsRepo, IModelsRepo, IUsageTracker
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
) -> FrogRateLimiterService:
    """Создаёт `FrogRateLimiterService` для ограничения частоты /frog."""
    rate_logger = logger.bind(module="FrogRateLimiterService")
    return FrogRateLimiterService(
        settings=app_settings,
        global_limiter=global_limiter,
        user_limiter=user_limiter,
        logger=rate_logger,
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
