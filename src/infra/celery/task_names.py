"""Перечисление имен задач Celery.

Централизует имена задач Celery для избежания магических строк в коде.
"""

from __future__ import annotations

from enum import StrEnum


class CeleryTaskNames(StrEnum):
    """Имена задач Celery для использования в send_task()."""

    WEDNESDAY_SEND_FROG_MANUAL = "wednesday.send_frog_manual"
