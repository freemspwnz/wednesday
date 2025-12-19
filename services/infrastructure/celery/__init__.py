"""Celery задачи и сервисы."""

# Импортируем задачи для их регистрации в Celery
from services.infrastructure.celery import tasks  # noqa: F401
from services.infrastructure.celery.app import celery_app
from services.infrastructure.celery.celery_task_queue import CeleryTaskQueue

__all__ = ["CeleryTaskQueue", "celery_app"]
