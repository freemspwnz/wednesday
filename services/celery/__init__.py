"""Celery задачи и сервисы."""

# Импортируем задачи для их регистрации в Celery
from services.celery import tasks  # noqa: F401
from services.celery.app import celery_app

__all__ = ["celery_app"]
