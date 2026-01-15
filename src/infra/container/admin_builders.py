"""Билдеры admin‑сервисов (доступ и команды админа, rate‑limit Telegram API)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.admin_access_service import AdminAccessService
from app.admin_command_service import AdminCommandService
from app.admin_notification_builders import AdminNotificationBuilders
from app.telegram_api_rate_limiter_service import TelegramAPIRateLimiterService
from shared.config import AppSettings
from shared.protocols.infrastructure import ILogger, IRateLimiter
from shared.protocols.repositories import IAdminsRepo, IUsageTracker

if TYPE_CHECKING:
    from app.chat_info_service import ChatInfoService
    from app.dispatch_delivery_service import DispatchDeliveryService
    from app.frog_limit_service import FrogRateLimiterService
    from app.image_service import ImageService
    from infra.repos.chats_repo import ChatsRepo


def build_admin_access_service(
    *,
    admins_repo: IAdminsRepo,
    super_admin_id: int | None,
    logger: ILogger,
) -> AdminAccessService:
    """Создаёт `AdminAccessService` с зависимостями."""
    access_logger = logger.bind(module="AdminAccessService")
    return AdminAccessService(
        admins_repo=admins_repo,
        super_admin_id=super_admin_id,
        logger=access_logger,
    )


def build_admin_command_service(  # noqa: PLR0913
    *,
    chats_repo: ChatsRepo,
    usage: IUsageTracker,
    admins_repo: IAdminsRepo,
    admin_access_service: AdminAccessService,
    logger: ILogger,
    # Опциональные зависимости для расширенной функциональности
    image_service: ImageService | None = None,
    frog_limit_service: FrogRateLimiterService | None = None,
    dispatch_delivery_service: DispatchDeliveryService | None = None,
    chat_info_service: ChatInfoService | None = None,
) -> AdminCommandService:
    """Создаёт `AdminCommandService` с зависимостями."""
    command_logger = logger.bind(module="AdminCommandService")
    notification_builders = AdminNotificationBuilders()
    return AdminCommandService(
        chats=chats_repo,
        usage=usage,
        admins_repo=admins_repo,
        admin_access_service=admin_access_service,
        logger=command_logger,
        image_service=image_service,
        frog_limit_service=frog_limit_service,
        dispatch_delivery_service=dispatch_delivery_service,
        chat_info_service=chat_info_service,
        notification_builders=notification_builders,
    )


def build_telegram_api_rate_limiter_service(
    *,
    app_settings: AppSettings,
    api_limiter: IRateLimiter,
    logger: ILogger,
) -> TelegramAPIRateLimiterService:
    """Создаёт `TelegramAPIRateLimiterService` для ограничения запросов к Telegram API."""
    rate_logger = logger.bind(module="TelegramAPIRateLimiterService")
    return TelegramAPIRateLimiterService(
        settings=app_settings,
        api_limiter=api_limiter,
        logger=rate_logger,
        max_parallel=app_settings.telegram_api_max_parallel_requests,
    )
