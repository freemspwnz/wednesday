"""Типизация контекста сервисов для Celery задач."""

from __future__ import annotations

from typing import Protocol

import asyncpg

from app.frog_processing_service import FrogProcessingService
from app.image_service import ImageService
from infra.redis.redis_client import RedisClient
from infra.repos.usage_tracker import UsageTracker

if False:  # TYPE_CHECKING
    from bot.wednesday_bot import WednesdayBot


class ServicesContext(Protocol):
    """Протокол для типизированного контекста сервисов Celery.

    Определяет структуру контекста, возвращаемого get_services_context().
    """

    bot: WednesdayBot
    postgres_pool: asyncpg.Pool
    redis_client: RedisClient
    image_service: ImageService
    usage_tracker: UsageTracker
    frog_processing: FrogProcessingService
