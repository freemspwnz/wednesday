"""Celery задачи и сервисы."""

from services.celery.app import celery_app

__all__ = ["celery_app"]
