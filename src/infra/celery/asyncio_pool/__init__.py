"""Асинхронная реализация Celery (pool=async)."""

from worker import celery_app

from .task_queue import CeleryTaskQueue

__all__ = ["CeleryTaskQueue", "celery_app"]
