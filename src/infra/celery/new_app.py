"""
Конфигурация Celery для Wednesday Frog Bot.

Использует Redis как брокер и backend для задач.
Поддерживает async задачи через celery[asyncio].
"""

from __future__ import annotations

import logging
import os

from celery import Celery
from celery.schedules import crontab

from infra.logging.logger import LoguruHandler, get_logger
from infra.redis.redis_client import get_redis_url
from shared.config import Config

# Создаём экземпляр Config при импорте модуля
config: Config = Config()

logger = get_logger(__name__)

# Получаем URL Redis для брокера и результата
# Используем get_redis_url(), который читает REDIS_HOST из переменных окружения
# В docker-compose.yml REDIS_HOST=redis установлен в секции environment
redis_url_initial = get_redis_url(config=config)
if not redis_url_initial or redis_url_initial.strip() == "":
    # Fallback на redis:6379 (правильный хост для Docker сети)
    redis_url_initial = "redis://redis:6379/0"
    logger.warning(f"get_redis_url() вернул пустое значение, используем fallback: {redis_url_initial}")
else:
    from urllib.parse import urlparse, urlunparse

    from infra.logging.logger import mask_secrets

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
# Используем Config
if isinstance(config, Config):
    celery_app.conf.timezone = config.scheduler.tz or "Europe/Amsterdam"
else:
    celery_app.conf.timezone = config.scheduler_tz or "Europe/Amsterdam"

# ⚠️ ВАЖНО: Celery Beat может игнорировать timezone, если system timezone = UTC
# или Docker контейнер не содержит /usr/share/zoneinfo
# Решение: добавить ENV TZ в Dockerfile и установить tzdata
# Также добавить проверку на старте beat (см. ниже)

# Настройки задач
celery_app.conf.task_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.result_serializer = "json"

# Настройки производительности для asyncio pool
# Оптимизация для работы с 1 ГБ RAM
if isinstance(config, Config):
    import os

    worker_prefetch = int(os.getenv("WORKER_PREFETCH_MULTIPLIER", "1"))
else:
    worker_prefetch = int(config._get_env_var("WORKER_PREFETCH_MULTIPLIER") or "1")
celery_app.conf.worker_prefetch_multiplier = worker_prefetch  # Не забиваем память задачами
celery_app.conf.task_acks_late = True  # Подтверждение после выполнения
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.result_expires = 3600  # Не хранить результаты долго (1 час)
celery_app.conf.task_track_started = True  # Позволяет видеть "Started" статус

# Настройка очередей для разделения задач
celery_app.conf.task_routes = {
    "wednesday.send_frog": {"queue": "wednesday"},
    "wednesday.send_frog_manual": {"queue": "wednesday"},
    "wednesday.generate_image": {"queue": "images"},
    "wednesday.daily_cleanup": {"queue": "maintenance"},
    "wednesday.daily_statistics": {"queue": "maintenance"},
}

# ⚠️ ВАЖНО: Dead Letter Queue для задач, которые упали после всех retry
if isinstance(config, Config):
    dlq_enabled = os.getenv("CELERY_DLQ_ENABLED") == "1"
else:
    dlq_enabled = config._get_env_var("CELERY_DLQ_ENABLED") == "1"

if dlq_enabled:
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
if isinstance(config, Config):
    beat_max_loop = int(os.getenv("BEAT_MAX_LOOP_INTERVAL", "10"))
    send_times = config.scheduler.send_times  # ["09:00", "12:00", "18:00"]
    wednesday_day = config.scheduler.wednesday_day  # 2 (среда)
else:
    beat_max_loop = int(config._get_env_var("BEAT_MAX_LOOP_INTERVAL") or "10")
    send_times = config.scheduler_send_times  # ["09:00", "12:00", "18:00"]
    wednesday_day = config.scheduler_wednesday_day  # 2 (среда)

celery_app.conf.beat_max_loop_interval = beat_max_loop

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

# Heartbeat задача для Beat healthcheck
beat_schedule["beat_heartbeat"] = {
    "task": "wednesday.beat_heartbeat",
    "schedule": 30.0,  # Каждые 30 секунд
    "options": {"queue": "maintenance"},
}

celery_app.conf.beat_schedule = beat_schedule

# ⚠️ ВАЖНО: Проверка timezone на старте beat
logger.info(f"Celery beat using timezone: {celery_app.conf.timezone}")
logger.info(f"System timezone: {os.environ.get('TZ', 'not set')}")

# Предупреждение, если timezone не совпадает
if os.environ.get('TZ') and os.environ.get('TZ') != celery_app.conf.timezone:
    logger.warning(f"Timezone mismatch: system TZ={os.environ.get('TZ')}, celery TZ={celery_app.conf.timezone}")

# Настройка Celery для использования Loguru
celery_app.conf.worker_log_format = "[%(asctime)s: %(levelname)s/%(processName)s] %(message)s"
celery_app.conf.worker_task_log_format = (
    "[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s"
)

# Подключаем Loguru handler к Celery logger
# НЕ устанавливаем уровень жёстко - пусть Celery сам управляет через --loglevel
celery_logger = logging.getLogger("celery")
celery_logger.handlers = [LoguruHandler()]


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
    import asyncio

    try:
        # Импортируем worker_ctx локально, чтобы избежать циклических зависимостей
        from infra.celery.new_context import worker_ctx

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


# ⚠️ ВАЖНО: Импортируем задачи в конце файла или через autodiscover_tasks
# Это необходимо для избежания циклических зависимостей
# Задачи должны быть определены в отдельном файле (new_tasks.py)
# и импортированы здесь или через autodiscover_tasks

# Импортируем новые задачи для регистрации в Celery
# Ленивый импорт в конце файла для избежания циклических зависимостей
try:
    from infra.celery import new_tasks  # noqa: F401

    logger.debug("Новые задачи Celery успешно импортированы")
except ImportError as e:
    logger.warning(f"Не удалось импортировать новые задачи Celery: {e}")
