"""Контейнер зависимостей для Telegram‑бота Wednesday Frog.

Инкапсулирует основные сервисы, чтобы передавать их в обработчики и другие
компоненты через явный DI, а не через context.application.bot_data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.admin_access_service import AdminAccessService
from app.admin_command_service import AdminCommandService
from app.admin_dashboard_service import AdminDashboardService
from app.admin_notification_service import AdminNotificationService
from app.chat_info_service import ChatInfoService
from app.database_operations_service import DatabaseOperationsService
from app.dispatch_service import DispatchService
from app.frog_limit_service import FrogRateLimiterService
from app.image_service import ImageService
from app.model_management_service import ModelManagementService
from app.telegram_api_rate_limiter_service import TelegramAPIRateLimiterService
from infra.cache.prompt_cache import PromptCache
from infra.cache.user_state_cache import UserStateCache
from infra.repos.dispatch_registry import DispatchRegistry
from shared.config import AppSettings
from shared.protocols.infrastructure import IMetrics
from shared.protocols.messaging import IMessagingService
from shared.protocols.repositories import IAdminsRepo, IChatsRepo, IUsageTracker

if TYPE_CHECKING:
    from shared.protocols.queues import ITaskQueue


@dataclass
class SupportBotServices:
    """Минимальный контейнер зависимостей для SupportBot.

    Содержит только необходимые сервисы для работы резервного бота:
    - admins_repo для проверки прав администратора
    - chats для обработки событий чата
    - settings для конфигурации
    - admin_notification_service для уведомлений администраторов

    Используется вместо полного BotServices для соблюдения принципа YAGNI
    и упрощения тестирования.

    Cleanup ресурсов (postgres_pool, redis_client) выполняется через
    фабрики в main.py, что исключает необходимость хранения инфраструктурных
    объектов в контейнере сервисов.
    """

    admins_repo: IAdminsRepo
    chats: IChatsRepo
    settings: AppSettings
    admin_notification_service: AdminNotificationService | None = None

    async def cleanup(self) -> None:
        """Закрывает ресурсы (если нужно).

        Минимальный cleanup для SupportBot. В отличие от BotServices,
        не закрывает клиенты изображений и текста, так как они не используются.
        Пулы подключений управляются через фабрики в main.py.
        """
        # Пулы подключений управляются через фабрики в main.py
        pass


@dataclass
class BotServices:
    """Явный контейнер зависимостей бота.

    Собирает в себе все основные сервисы, которые ранее прокидывались разрозненно
    через атрибуты `WednesdayBot` и `context.application.bot_data`.

    Cleanup ресурсов (postgres_pool, redis_client) выполняется через
    фабрики в main.py, что исключает необходимость хранения инфраструктурных
    объектов в контейнере сервисов и предотвращает протечку абстракции
    инфраструктурного слоя.
    """

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
    chat_info_service: ChatInfoService | None = None
    dispatch_service: DispatchService | None = None
    messaging_service: IMessagingService | None = None
    database_operations: DatabaseOperationsService | None = None
    admins_repo: IAdminsRepo | None = None
    telegram_api_rate_limiter: TelegramAPIRateLimiterService | None = None

    async def cleanup(self) -> None:  # noqa: PLR6301
        """Закрывает все ресурсы (HTTP сессии, соединения).

        Должен вызываться при остановке приложения для корректного
        освобождения всех ресурсов.

        Side Effects:
            - Закрывает ImageClientContainer через aclose()
            - Закрывает TextClientContainer через aclose()
            - Пулы подключений управляются через фабрики в main.py
        """
        from infra.clients import get_image_client_container, get_text_client_container
        from infra.logging.logger import get_logger

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

        # Пулы подключений управляются через фабрики в main.py


def require_bot_services(
    services: BotServices | SupportBotServices,
    handler_name: str,
) -> BotServices:
    """Проверяет, что services является BotServices, и возвращает его.

    Используется для валидации типа в конструкторах обработчиков, которые требуют
    полный BotServices, а не минимальный SupportBotServices.

    Args:
        services: Контейнер сервисов (может быть BotServices или SupportBotServices).
        handler_name: Имя класса-обработчика для сообщения об ошибке.

    Returns:
        Экземпляр BotServices (гарантированно после проверки типа).

    Raises:
        TypeError: Если services не является экземпляром BotServices.
    """
    if not isinstance(services, BotServices):
        raise TypeError(
            f"{handler_name} requires BotServices, got {type(services).__name__}",
        )
    return services
