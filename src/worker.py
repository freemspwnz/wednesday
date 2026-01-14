"""
Конфигурация Celery для Wednesday Frog Bot (async реализация).

Использует Redis как брокер и backend для задач.
Поддерживает async задачи через celery-pool-asyncio.
"""

from __future__ import annotations

import asyncio
import logging
import os

from celery import Celery

from infra.celery.asyncio_pool.config import CeleryConfig, get_celery_redis_url
from infra.logging.logger import LoguruHandler, get_logger

logger = get_logger(__name__)

# Получаем URL Redis для брокера и результата

redis_url_initial = get_celery_redis_url()

# Создаём экземпляр Celery
celery_app = Celery(
    "wednesday_bot",
    broker=redis_url_initial,
    backend=redis_url_initial,
)

# Загружаем конфигурацию из celery_config
celery_app.config_from_object(CeleryConfig())

# Настройка Celery для использования Loguru
celery_logger = logging.getLogger("celery")
celery_logger.handlers = [LoguruHandler()]


# ⚠️ ВАЖНО: Обработчик worker_ready для проверки конфигурации
@celery_app.signals.worker_ready.connect
def _on_worker_ready(sender: object | None = None, **kwargs: object) -> None:
    """Обработчик готовности worker. Проверяет конфигурацию timezone.

    Выполняется только при запуске worker, а не при каждом импорте модуля.
    """
    logger.info(f"Celery beat using timezone: {celery_app.conf.timezone}")
    logger.info(f"System timezone: {os.environ.get('TZ', 'not set')}")

    # Предупреждение, если timezone не совпадает
    if os.environ.get('TZ') and os.environ.get('TZ') != celery_app.conf.timezone:
        logger.warning(f"Timezone mismatch: system TZ={os.environ.get('TZ')}, celery TZ={celery_app.conf.timezone}")


# ⚠️ ВАЖНО: Обработчик shutdown для очистки ресурсов
# Импортируем worker_ctx локально, чтобы избежать циклических зависимостей
@celery_app.signals.worker_shutdown.connect
def _on_worker_shutdown(sender: object | None = None, **kwargs: object) -> None:
    """Обработчик остановки worker. Гарантирует выполнение cleanup ресурсов.

    Для celery[asyncio] всегда есть running event loop, поэтому используем create_task().
    asyncio.run() не может быть вызван из running loop и вызовет RuntimeError.

    ⚠️ ВАЖНО: В режиме --pool=asyncio сигнал обрабатывается в асинхронном контексте,
    поэтому можно безопасно использовать asyncio.get_running_loop() и create_task().
    """
    try:
        # Импортируем worker_ctx локально, чтобы избежать циклических зависимостей
        from infra.celery.asyncio_pool.context import worker_ctx

        # Для celery[asyncio] всегда есть running event loop
        loop = asyncio.get_running_loop()
        if not loop.is_closed():
            # Создаём задачу для graceful shutdown
            # В asyncio pool задача будет выполнена до завершения worker процесса
            _ = loop.create_task(worker_ctx.close())  # noqa: RUF006
            logger.info(
                "Задача закрытия ресурсов воркера создана",
                event="celery_shutdown_task_created",
                status="started",
            )
            # Celery дождется завершения всех задач перед shutdown
        else:
            logger.warning(
                "Event loop is closed, cannot perform graceful shutdown",
                event="celery_shutdown_loop_closed",
                status="warning",
            )
    except RuntimeError as e:
        # Нет running loop - это не должно происходить в asyncio pool
        logger.warning(
            f"No running event loop, cannot perform graceful shutdown: {e}",
            event="celery_shutdown_no_loop",
            status="warning",
        )
    except Exception as e:
        logger.error(
            f"Ошибка при вызове shutdown в worker_shutdown handler: {e}",
            event="celery_shutdown_handler_error",
            status="error",
            error_type=type(e).__name__,
            error_message=str(e),
            exc_info=True,
        )


# Автоматически обнаруживаем и регистрируем задачи из модуля tasks
celery_app.autodiscover_tasks(['infra.celery.asyncio_pool.tasks'])
