"""Celery задачи и сервисы."""

from infra.celery.app import celery_app
from infra.celery.celery_task_queue import CeleryTaskQueue

# ⚠️ ВАЖНО: НЕ импортируем tasks здесь, чтобы избежать циклического импорта.
# Tasks регистрируются автоматически при импорте tasks.py в worker процессе.
# Для явной регистрации tasks импортируйте их в точке входа worker:
#   from infra.celery import tasks

__all__ = ["CeleryTaskQueue", "celery_app"]
