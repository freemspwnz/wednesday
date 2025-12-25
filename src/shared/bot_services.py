"""Контейнер зависимостей для Telegram‑бота Wednesday Frog.

Инкапсулирует основные сервисы, чтобы передавать их в обработчики и другие
компоненты через явный DI, а не через context.application.bot_data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import asyncpg

from app.admin_access_service import AdminAccessService
from app.admin_command_service import AdminCommandService
from app.admin_dashboard_service import AdminDashboardService
from app.admin_notification_service import AdminNotificationService
from app.database_operations_service import DatabaseOperationsService
from app.dispatch_service import DispatchService
from app.frog_limit_service import FrogRateLimiterService
from app.image_service import ImageService
from app.model_management_service import ModelManagementService
from infra.cache.prompt_cache import PromptCache
from infra.cache.user_state_cache import UserStateCache
from infra.repos.dispatch_registry import DispatchRegistry
from shared.config import AppSettings
from shared.protocols import (
    IAdminsRepo,
    IBotController,
    IChatsRepo,
    IMessagingService,
    IMetrics,
    IUsageTracker,
)

if TYPE_CHECKING:
    from infra.redis.redis_client import RedisClient
    from shared.protocols import ITaskQueue


@dataclass
class BotServices:
    """Явный контейнер зависимостей бота.

    Собирает в себе все основные сервисы, которые ранее прокидывались разрозненно
    через атрибуты `WednesdayBot` и `context.application.bot_data`.
    """

    # Инфраструктурные зависимости (ОБЯЗАТЕЛЬНЫЕ)
    postgres_pool: asyncpg.Pool
    redis_client: RedisClient

    usage: IUsageTracker
    chats: IChatsRepo
    dispatch_registry: DispatchRegistry
    metrics: IMetrics
    prompt_cache: PromptCache
    user_state_store: UserStateCache
    settings: AppSettings
    image_service: ImageService
    frog_rate_limiter: FrogRateLimiterService
    task_queue: ITaskQueue
    admin_dashboard_service: AdminDashboardService | None = None
    model_management_service: ModelManagementService | None = None
    admin_access_service: AdminAccessService | None = None
    admin_command_service: AdminCommandService | None = None
    admin_notification_service: AdminNotificationService | None = None
    bot_controller: IBotController | None = None  # для команд управления ботом, например /stop
    dispatch_service: DispatchService | None = None
    messaging_service: IMessagingService | None = None
    database_operations: DatabaseOperationsService | None = None
    admins_repo: IAdminsRepo | None = None

    async def cleanup(self) -> None:  # noqa: PLR6301
        """Закрывает все ресурсы (HTTP сессии, соединения).

        Должен вызываться при остановке приложения для корректного
        освобождения всех ресурсов.

        Side Effects:
            - Закрывает ImageClientContainer через aclose()
            - Закрывает TextClientContainer через aclose()
            - Закрывает Redis соединения через close_redis()
            - Закрывает PostgreSQL pool через close_postgres_pool()
        """
        from infra.clients import get_image_client_container, get_text_client_container
        from infra.database.postgres_client import close_postgres_pool
        from infra.logging.logger import get_logger
        from infra.redis.redis_client import close_redis

        logger = get_logger(__name__)

        # Закрываем клиенты через контейнеры
        try:
            image_container = get_image_client_container()
            await image_container.aclose()
            logger.info("ImageClientContainer закрыт через BotServices.cleanup()")
        except Exception as e:
            logger.warning(f"Ошибка при закрытии ImageClientContainer: {e}")

        try:
            text_container = get_text_client_container()
            await text_container.aclose()
            logger.info("TextClientContainer закрыт через BotServices.cleanup()")
        except Exception as e:
            logger.warning(f"Ошибка при закрытии TextClientContainer: {e}")

        # Закрываем Redis соединения
        try:
            await close_redis()
            logger.info("Redis соединения закрыты через BotServices.cleanup()")
        except Exception as e:
            logger.warning(f"Ошибка при закрытии Redis: {e}")

        # Закрываем PostgreSQL pool
        try:
            await close_postgres_pool()
            logger.info("PostgreSQL pool закрыт через BotServices.cleanup()")
        except Exception as e:
            logger.warning(f"Ошибка при закрытии PostgreSQL pool: {e}")
