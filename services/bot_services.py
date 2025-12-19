"""Контейнер зависимостей для Telegram‑бота Wednesday Frog.

Инкапсулирует основные сервисы, чтобы передавать их в обработчики и другие
компоненты через явный DI, а не через context.application.bot_data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from services.app_settings import AppSettings
from services.application.admin_dashboard_service import AdminDashboardService
from services.application.dispatch_service import DispatchService
from services.application.frog_limit_service import FrogRateLimiterService
from services.application.image_service import ImageService
from services.infrastructure.cache.prompt_cache import PromptCache
from services.infrastructure.cache.user_state_cache import UserStateCache
from services.protocols import IChatsRepo, IUsageTracker
from utils.dispatch_registry import DispatchRegistry
from utils.metrics import Metrics

if TYPE_CHECKING:
    from bot.wednesday_bot import WednesdayBot
    from services.application.frog_requests import FrogRequestService


@dataclass
class BotServices:
    """Явный контейнер зависимостей бота.

    Собирает в себе все основные сервисы, которые ранее прокидывались разрозненно
    через атрибуты `WednesdayBot` и `context.application.bot_data`.
    """

    usage: IUsageTracker
    chats: IChatsRepo
    dispatch_registry: DispatchRegistry
    metrics: Metrics
    prompt_cache: PromptCache
    user_state_store: UserStateCache
    settings: AppSettings
    image_service: ImageService
    frog_rate_limiter: FrogRateLimiterService
    frog_request_service: FrogRequestService
    admin_dashboard_service: AdminDashboardService | None = None
    bot_controller: WednesdayBot | None = None  # для команд управления ботом, например /stop
    dispatch_service: DispatchService | None = None

    async def cleanup(self) -> None:  # noqa: PLR6301
        """Закрывает все ресурсы (HTTP сессии, соединения).

        Должен вызываться при остановке приложения для корректного
        освобождения всех ресурсов.

        Side Effects:
            - Закрывает ImageClientContainer через aclose()
            - Закрывает TextClientContainer через aclose()
            - В будущем: закрытие Redis соединений, PostgreSQL pool и т.д.
        """
        from services.clients import get_image_client_container, get_text_client_container
        from utils.logger import get_logger

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

        # В будущем можно добавить cleanup для других ресурсов:
        # - Redis connections (если требуется явное закрытие)
        # - PostgreSQL pool (если используется через BotServices)
        # - И другие долгоживущие ресурсы
