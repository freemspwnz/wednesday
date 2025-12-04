"""
Отдельный Celery app для тестов.

Полностью изолирован от production кода:
- Не импортирует бот, сервисы, production задачи
- Использует только базовые утилиты (config, redis_client)
- Имеет тестовые очереди по умолчанию
- Регистрирует только test.ping задачу
"""

from celery import Celery

from utils.redis_client import get_redis_url

# Получаем URL Redis для брокера и результата
redis_url = get_redis_url() or "redis://localhost:6379/0"

# Создаём отдельный Celery app для тестов
celery_app_test = Celery(
    "wednesday_bot_test",
    broker=redis_url,
    backend=redis_url,
)

# Минимальная конфигурация для тестов
celery_app_test.conf.task_serializer = "json"
celery_app_test.conf.accept_content = ["json"]
celery_app_test.conf.result_serializer = "json"
celery_app_test.conf.task_acks_late = True
celery_app_test.conf.task_track_started = True

# Тестовые очереди по умолчанию
celery_app_test.conf.task_routes = {
    "test.ping": {"queue": "test_main"},
}

# Импортируем test.ping задачу для регистрации
from services.celery_tasks_test import test_ping  # noqa: E402, F401
