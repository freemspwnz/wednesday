#!/usr/bin/env python3
"""
Скрипт для запуска Celery worker с asyncio pool через Python API.

Этот скрипт используется для production, где asyncio pool не поддерживается
через командную строку в Celery 5.5.3, но доступен через Python API.
"""

import sys
from pathlib import Path

# Добавляем /app в PYTHONPATH для импорта модулей проекта
app_dir = Path(__file__).parent.parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from services.celery_app import celery_app  # noqa: E402

if __name__ == "__main__":
    # Запускаем worker с asyncio pool через Python API
    # Это эквивалентно: celery -A services.celery_app worker --pool=asyncio
    celery_app.worker_main(
        [
            "--pool=asyncio",
            "--loglevel=info",
            "--concurrency=8",
            "-Q",
            "wednesday,images,maintenance",
        ]
        + sys.argv[1:]
    )  # Позволяем передавать дополнительные аргументы
