"""
Конфигурация Celery для Wednesday Frog Bot.

Использует Redis как брокер и backend для задач.
Поддерживает async задачи через celery[asyncio].
"""

import logging
import os
import sys
from types import FrameType

from celery import Celery
from celery.schedules import crontab

from utils.config import config
from utils.logger import get_logger
from utils.redis_client import get_redis_url

logger = get_logger(__name__)

# Получаем URL Redis для брокера и результата
# Используем get_redis_url(), который читает REDIS_HOST из переменных окружения
# В docker-compose.yml REDIS_HOST=redis установлен в секции environment
redis_url_initial = get_redis_url()
if not redis_url_initial or redis_url_initial.strip() == "":
    # Fallback на redis:6379 (правильный хост для Docker сети)
    redis_url_initial = "redis://redis:6379/0"
    logger.warning(f"get_redis_url() вернул пустое значение, используем fallback: {redis_url_initial}")
else:
    from urllib.parse import urlparse, urlunparse

    from utils.logger import mask_secrets

    # Маскируем пароль в URL перед логированием
    parsed = urlparse(redis_url_initial)
    if parsed.password:
        # Заменяем пароль на маскированное значение
        masked_netloc = parsed.netloc.replace(f":{parsed.password}@", ":****@")
        masked_url = urlunparse(parsed._replace(netloc=masked_netloc))
        logger.info(f"Celery использует Redis URL: {masked_url}")
    else:
        logger.info(f"Celery использует Redis URL: {mask_secrets(redis_url_initial)}")


celery_app = Celery(
    "wednesday_bot",
    broker=redis_url_initial,
    backend=redis_url_initial,
)

# ВАЖНО: Принудительно устанавливаем все broker URL параметры сразу после создания app
# Celery может неправильно парсить URL с паролем при создании Connection,
# поэтому устанавливаем все параметры явно
# get_redis_url() читает переменные окружения в момент импорта модуля,
# поэтому дополнительное обновление через сигналы не требуется
celery_app.conf.broker_url = redis_url_initial
celery_app.conf.broker = redis_url_initial
celery_app.conf.result_backend = redis_url_initial
celery_app.conf.broker_read_url = redis_url_initial
celery_app.conf.broker_write_url = redis_url_initial

# Настройка таймзон
celery_app.conf.enable_utc = False
celery_app.conf.timezone = config.scheduler_tz or "Europe/Amsterdam"

# ⚠️ ВАЖНО: Celery Beat может игнорировать timezone, если system timezone = UTC
# или Docker контейнер не содержит /usr/share/zoneinfo
# Решение: добавить ENV TZ в Dockerfile и установить tzdata
# Также добавить проверку на старте beat (см. ниже)

# Настройки задач
celery_app.conf.task_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.result_serializer = "json"

# Настройки производительности
celery_app.conf.worker_prefetch_multiplier = int(config._get_env_var("WORKER_PREFETCH_MULTIPLIER") or "1")
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_max_tasks_per_child = 50  # Избегает memory leaks
celery_app.conf.task_track_started = True  # Позволяет видеть "Started" статус

# Настройка очередей для разделения задач
celery_app.conf.task_routes = {
    "wednesday.send_frog": {"queue": "wednesday"},
    "wednesday.generate_image": {"queue": "images"},
    "wednesday.daily_cleanup": {"queue": "maintenance"},
    "wednesday.daily_statistics": {"queue": "maintenance"},
}

# ⚠️ ВАЖНО: Dead Letter Queue для задач, которые упали после всех retry
if config._get_env_var("CELERY_DLQ_ENABLED") == "1":
    celery_app.conf.task_routes.update({
        "wednesday.send_frog": {
            "queue": "wednesday",
            "routing_key": "wednesday",
            "exchange": "celery",
        },
    })
    # Настройка DLQ
    celery_app.conf.task_reject_on_worker_lost = True
    celery_app.conf.task_acks_late = True

# Настройка Beat
celery_app.conf.beat_max_loop_interval = int(config._get_env_var("BEAT_MAX_LOOP_INTERVAL") or "10")

# Парсим времена отправки из конфигурации
send_times = config.scheduler_send_times  # ["09:00", "12:00", "18:00"]
wednesday_day = config.scheduler_wednesday_day  # 2 (среда)

# Создаём расписание для каждого временного слота
beat_schedule = {}

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

celery_app.conf.beat_schedule = beat_schedule

# ⚠️ ВАЖНО: Проверка timezone на старте beat
logger.info(f"Celery beat using timezone: {celery_app.conf.timezone}")
logger.info(f"System timezone: {os.environ.get('TZ', 'not set')}")

# Предупреждение, если timezone не совпадает
if os.environ.get('TZ') and os.environ.get('TZ') != celery_app.conf.timezone:
    logger.warning(f"Timezone mismatch: system TZ={os.environ.get('TZ')}, celery TZ={celery_app.conf.timezone}")

# Настройка логирования Celery через Loguru


class LoguruHandler(logging.Handler):
    """Адаптер для использования Loguru в Celery."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: PLR6301
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            # Если levelname не распознан, используем числовой уровень
            level_int = record.levelno
            # Преобразуем в строку для loguru (используем константы logging)
            if level_int >= logging.CRITICAL:  # 50
                level = "CRITICAL"
            elif level_int >= logging.ERROR:  # 40
                level = "ERROR"
            elif level_int >= logging.WARNING:  # 30
                level = "WARNING"
            elif level_int >= logging.INFO:  # 20
                level = "INFO"
            elif level_int >= logging.DEBUG:  # 10
                level = "DEBUG"
            else:
                level = "TRACE"

        frame: FrameType | None = sys._getframe(6)
        depth = 6
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# Настройка Celery для использования Loguru
celery_app.conf.worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
celery_app.conf.worker_task_log_format = (
    "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s"
)

# Подключаем Loguru handler к Celery logger
# НЕ устанавливаем уровень жёстко - пусть Celery сам управляет через --loglevel
celery_logger = logging.getLogger("celery")
celery_logger.handlers = [LoguruHandler()]
