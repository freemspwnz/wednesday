"""
Отдельный Celery app для тестов.

Полностью изолирован от production кода:
- Не импортирует бот, сервисы, production задачи
- Не использует боевой config и utils.redis_client
- Конфигурируется только через тестовые переменные окружения
- Имеет тестовые очереди по умолчанию
- Регистрирует только test.ping задачу
"""

from celery import Celery

from utils.config_test import config_test

# Получаем URL Redis для брокера и результата из тестового тестового конфига
redis_url = config_test.celery_test_redis_url

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
from tests.common.celery_tasks_test import ping_task  # noqa: E402, F401
