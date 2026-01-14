"""Билдеры сервисов для Celery‑воркеров.

Переносит функциональность из старого `infra.container` для:
- `build_celery_services_context`
- `build_cleanup_service`
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import asyncpg

from infra.celery.cleanup_service import CleanupService
from infra.clients.image_client_container import get_image_client_container
from infra.clients.text_client_container import get_text_client_container
from infra.database.postgres_client import PostgresPoolFactory
from infra.redis.redis_client import RedisClient, RedisClientFactory
from shared.config import Config
from shared.protocols.infrastructure import ILogger

if TYPE_CHECKING:
    from infra.repos.usage_tracker import UsageTracker
    from shared.protocols.services import IFrogProcessingService, IImageService


class CeleryServicesContext(TypedDict, total=False):
    """Типизированный контекст сервисов, используемых Celery задачами."""

    postgres_pool: asyncpg.Pool
    redis_client: RedisClient
    image_service: IImageService
    usage_tracker: UsageTracker
    frog_processing: IFrogProcessingService


def build_celery_services_context(
    *,
    config: Config,
    db_pool: asyncpg.Pool,
    redis_client: RedisClient,
) -> CeleryServicesContext:
    """Создаёт контекст сервисов для Celery‑задач.

    ⚠️ Внимание: реализовано минимально, чтобы сохранить совместимость
    с существующим интерфейсом `get_services_context`. Детальная сборка
    сервисов для Celery сейчас делается через общие фабрики в основном контейнере,
    поэтому здесь контекст ограничен базовыми ресурсами, которые реально используются.
    """
    # Отложенный импорт, чтобы не тянуть зависимости на верхний уровень модуля.

    context: CeleryServicesContext = CeleryServicesContext()
    # В старой версии здесь создавался Telegram‑бот и полный стек сервисов.
    # Сейчас Celery‑задачи используют более узкий набор протоколов,
    # поэтому оставляем только пулы и клиента Redis.
    context["postgres_pool"] = db_pool
    context["redis_client"] = redis_client

    # Заглушки для image_service / usage_tracker / frog_processing:
    # они должны поставляться через протоколы из слоёв app/domain при необходимости.
    return context


def build_cleanup_service(
    *,
    logger: ILogger,
    pool_factory: PostgresPoolFactory,
    redis_factory: RedisClientFactory,
) -> CleanupService:
    """Создаёт `CleanupService` для graceful shutdown Celery‑ресурсов."""
    return CleanupService(
        logger=logger,
        image_client_container=get_image_client_container(),
        text_client_container=get_text_client_container(),
        pool_factory=pool_factory,
        redis_factory=redis_factory,
    )
