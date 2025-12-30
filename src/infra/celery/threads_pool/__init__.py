"""Синхронная реализация Celery (pool=threads)."""

from infra.celery.sync.app import celery_app
from infra.celery.sync.celery_task_queue import CeleryTaskQueue

__all__ = ["CeleryTaskQueue", "celery_app"]
