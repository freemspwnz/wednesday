#!/usr/bin/env python3
"""
Healthcheck скрипт для Celery worker через inspect() API.

Проверяет, что worker не просто запущен, но и готов обрабатывать задачи.
"""

import sys
from pathlib import Path

# Добавляем /app в PYTHONPATH для импорта модулей проекта
app_dir = Path(__file__).parent.parent
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from services.celery_app import celery_app  # noqa: E402


def check_worker_health() -> int:
    """
    Проверяет здоровье Celery worker через inspect() API.

    Returns:
        0 если worker здоров и готов, 1 если нет
    """
    try:
        # Используем inspect API для проверки доступности worker'ов
        inspect = celery_app.control.inspect(timeout=2)

        # Пингуем worker'ы
        ping_result = inspect.ping()

        if not ping_result:
            # Нет доступных worker'ов
            return 1

        # Проверяем, что есть хотя бы один активный worker
        active_workers = inspect.active()
        if not active_workers or len(active_workers) == 0:
            return 1

        # Worker здоров и готов обрабатывать задачи
        return 0
    except Exception as e:
        # Любая ошибка означает, что worker не готов
        print(f"Healthcheck failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(check_worker_health())
