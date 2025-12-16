"""Контейнер зависимостей для Telegram‑бота Wednesday Frog.

Инкапсулирует основные сервисы, чтобы передавать их в обработчики и другие
компоненты через явный DI, а не через context.application.bot_data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from services.app_settings import AppSettings

if TYPE_CHECKING:
    from bot.wednesday_bot import WednesdayBot
from services.image_generator import ImageGenerator
from services.prompt_cache import PromptCache
from services.rate_limiter import RateLimiter
from services.scheduler import TaskScheduler
from services.user_state_store import UserStateStore
from utils.chats_store import ChatsStore
from utils.dispatch_registry import DispatchRegistry
from utils.metrics import Metrics
from utils.usage_tracker import UsageTracker


@dataclass
class BotServices:
    """Явный контейнер зависимостей бота.

    Собирает в себе все основные сервисы, которые ранее прокидывались разрозненно
    через атрибуты `WednesdayBot` и `context.application.bot_data`.
    """

    image_generator: ImageGenerator
    scheduler: TaskScheduler | None
    usage: UsageTracker
    chats: ChatsStore
    dispatch_registry: DispatchRegistry
    metrics: Metrics
    prompt_cache: PromptCache
    user_state_store: UserStateStore
    rate_limiter: RateLimiter
    settings: AppSettings
    bot_controller: WednesdayBot | None = None  # для команд управления ботом, например /stop
