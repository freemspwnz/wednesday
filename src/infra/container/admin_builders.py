"""Билдеры admin‑сервисов (доступ и команды админа, rate‑limit Telegram API)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.admin_access_service import AdminAccessService
from app.admin_command_service import AdminCommandService
from app.telegram_api_rate_limiter_service import TelegramAPIRateLimiterService
from shared.config import AppSettings
from shared.protocols.infrastructure import ILogger, IRateLimiter
from shared.protocols.repositories import IAdminsRepo, IUsageTracker

if TYPE_CHECKING:
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


def build_admin_command_service(
    *,
    chats_repo: ChatsRepo,
    usage: IUsageTracker,
    admins_repo: IAdminsRepo,
    admin_access_service: AdminAccessService,
    logger: ILogger,
) -> AdminCommandService:
    """Создаёт `AdminCommandService` с зависимостями."""
    command_logger = logger.bind(module="AdminCommandService")
    return AdminCommandService(
        chats=chats_repo,
        usage=usage,
        admins_repo=admins_repo,
        admin_access_service=admin_access_service,
        logger=command_logger,
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
