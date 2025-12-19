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
from utils.chats_repo import ChatsRepo
from utils.dispatch_registry import DispatchRegistry
from utils.metrics import Metrics
from utils.usage_tracker import UsageTracker

if TYPE_CHECKING:
    from bot.wednesday_bot import WednesdayBot
    from services.application.frog_requests import FrogRequestService


@dataclass
class BotServices:
    """Явный контейнер зависимостей бота.

    Собирает в себе все основные сервисы, которые ранее прокидывались разрозненно
    через атрибуты `WednesdayBot` и `context.application.bot_data`.
    """

    usage: UsageTracker
    chats: ChatsRepo
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
