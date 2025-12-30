"""Конфигурация Celery для async реализации."""

from __future__ import annotations

import os
from typing import Any, ClassVar

from celery.schedules import crontab

from infra.logging.logger import get_logger
from infra.redis.redis_client import get_redis_url
from shared.config import Config

# Создаём экземпляр Config при импорте модуля
config: Config = Config()
logger = get_logger(__name__)


def get_celery_redis_url() -> str:
    """Получает URL Redis для Celery брокера и backend.

    Использует get_redis_url() из infra.redis.redis_client, который читает
    REDIS_HOST из переменных окружения. В docker-compose.yml REDIS_HOST=redis
    установлен в секции environment.

    Returns:
        URL Redis для использования в Celery. Если get_redis_url() вернул пустое
        значение, возвращает fallback "redis://redis:6379/0" (правильный хост для Docker сети).
    """
    redis_url = get_redis_url(config=config)
    if not redis_url or redis_url.strip() == "":
        # Fallback на redis:6379 (правильный хост для Docker сети)
        redis_url = "redis://redis:6379/0"
        logger.warning(f"get_redis_url() вернул пустое значение, используем fallback: {redis_url}")
    else:
        logger.info(f"Celery использует Redis URL: {redis_url}")
    return redis_url


def get_task_routes() -> dict[str, dict[str, Any]]:
    """Возвращает словарь маршрутизации задач по очередям."""
    routes: dict[str, dict[str, Any]] = {
        "wednesday.send_frog": {"queue": "wednesday"},
        "wednesday.send_frog_manual": {"queue": "wednesday"},
        "wednesday.generate_image": {"queue": "images"},
        "wednesday.daily_cleanup": {"queue": "maintenance"},
        "wednesday.daily_statistics": {"queue": "maintenance"},
    }

    # Dead Letter Queue для задач, которые упали после всех retry
    if isinstance(config, Config):
        dlq_enabled = os.getenv("CELERY_DLQ_ENABLED") == "1"
    else:
        dlq_enabled = config._get_env_var("CELERY_DLQ_ENABLED") == "1"

    if dlq_enabled:
        routes.update({
            "wednesday.send_frog": {
                "queue": "wednesday",
                "routing_key": "wednesday",
                "exchange": "celery",
            },
        })

    return routes


def get_beat_schedule() -> dict[str, dict[str, Any]]:
    """Возвращает расписание задач для Celery Beat."""
    if isinstance(config, Config):
        send_times = config.scheduler.send_times  # ["09:00", "12:00", "18:00"]
        wednesday_day = config.scheduler.wednesday_day  # 2 (среда)
    else:
        send_times = config.scheduler_send_times  # ["09:00", "12:00", "18:00"]
        wednesday_day = config.scheduler_wednesday_day  # 2 (среда)

    # Создаём расписание для каждого временного слота
    beat_schedule: dict[str, dict[str, Any]] = {}

    for time_str in send_times:
        h, m = map(int, time_str.split(":"))
        task_name = f"wednesday_frog_{time_str.replace(':', '_')}"

        beat_schedule[task_name] = {
            "task": "wednesday.send_frog",
            "schedule": crontab(
                day_of_week=wednesday_day,  # 2 = среда
                hour=h,
                minute=m,
            ),
            "args": (time_str,),  # Передаём slot_time
            "options": {"queue": "wednesday"},  # ⚠️ УЛУЧШЕНО: явно указываем очередь для уникальности
        }

    # Ежедневные задачи
    beat_schedule["daily_cleanup"] = {
        "task": "wednesday.daily_cleanup",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "maintenance"},
    }

    beat_schedule["daily_statistics"] = {
        "task": "wednesday.daily_statistics",
        "schedule": crontab(hour=4, minute=0),
        "options": {"queue": "maintenance"},
    }

    # Heartbeat задача для Beat healthcheck
    beat_schedule["beat_heartbeat"] = {
        "task": "wednesday.beat_heartbeat",
        "schedule": 30.0,  # Каждые 30 секунд
        "options": {"queue": "maintenance"},
    }

    return beat_schedule


class CeleryConfig:
    """Класс конфигурации для Celery config_from_object."""

    # Настройка таймзон
    enable_utc = False
    timezone: str

    # Настройки задач
    task_serializer = "json"
    accept_content: ClassVar[list[str]] = ["json"]
    result_serializer = "json"

    # Настройки производительности для asyncio pool
    # Оптимизация для работы с 1 ГБ RAM
    task_acks_late = True  # Подтверждение после выполнения
    task_reject_on_worker_lost = True
    result_expires = 3600  # Не хранить результаты долго (1 час)
    task_track_started = True  # Позволяет видеть "Started" статус

    # Настройка Beat
    beat_max_loop_interval: int

    # Настройки логирования
    worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
    worker_task_log_format = "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s"

    def __init__(self) -> None:
        """Инициализирует конфигурацию."""
        # Используем Config
        if isinstance(config, Config):
            self.timezone = config.scheduler.tz or "Europe/Amsterdam"
            worker_prefetch = int(os.getenv("WORKER_PREFETCH_MULTIPLIER", "1"))
            self.beat_max_loop_interval = int(os.getenv("BEAT_MAX_LOOP_INTERVAL", "10"))
        else:
            self.timezone = config.scheduler_tz or "Europe/Amsterdam"
            worker_prefetch = int(config._get_env_var("WORKER_PREFETCH_MULTIPLIER") or "1")
            self.beat_max_loop_interval = int(config._get_env_var("BEAT_MAX_LOOP_INTERVAL") or "10")

        self.worker_prefetch_multiplier = worker_prefetch  # Не забиваем память задачами

        # Настройка очередей для разделения задач
        self.task_routes = get_task_routes()

        # Расписание задач для Beat
        self.beat_schedule = get_beat_schedule()
