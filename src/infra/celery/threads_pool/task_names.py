"""Перечисление имен задач Celery.

Централизует имена задач Celery для избежания магических строк в коде.
"""

from __future__ import annotations

from enum import StrEnum


class CeleryTaskNames(StrEnum):
    """Имена задач Celery для использования в send_task()."""

    # Старые задачи (для обратной совместимости)
    WEDNESDAY_SEND_FROG_MANUAL = "wednesday.send_frog_manual"

    # Новые задачи с новой реализацией через WorkerContext
    NEW_SEND_FROG = "wednesday.new_send_frog"
    NEW_GENERATE_IMAGE = "wednesday.new_generate_image"
    NEW_DAILY_CLEANUP = "wednesday.new_daily_cleanup"
