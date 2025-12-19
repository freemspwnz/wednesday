"""Celery задачи и сервисы."""

from services.infrastructure.celery.app import celery_app
from services.infrastructure.celery.celery_task_queue import CeleryTaskQueue

# ⚠️ ВАЖНО: НЕ импортируем tasks здесь, чтобы избежать циклического импорта.
# Tasks регистрируются автоматически при импорте tasks.py в worker процессе.
# Для явной регистрации tasks импортируйте их в точке входа worker:
#   from services.infrastructure.celery import tasks

__all__ = ["CeleryTaskQueue", "celery_app"]
