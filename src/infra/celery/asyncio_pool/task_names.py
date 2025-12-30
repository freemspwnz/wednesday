"""Перечисление имен задач Celery.

Централизует имена задач Celery для избежания магических строк в коде.
"""

from __future__ import annotations

from enum import StrEnum


class CeleryTaskNames(StrEnum):
    """Имена задач Celery для использования в send_task()."""

    # Задачи async реализации
    SEND_FROG = "wednesday.send_frog"
    SEND_FROG_MANUAL = "wednesday.send_frog_manual"
    GENERATE_IMAGE = "wednesday.generate_image"
    DAILY_CLEANUP = "wednesday.daily_cleanup"
