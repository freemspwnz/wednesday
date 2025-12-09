"""
Тестовые Celery задачи для проверки готовности worker.

Эти задачи не импортируют сервисы бота, не используют БД,
используются только для healthcheck в E2E тестах.
"""

from tests.common.celery_app_test import celery_app_test


@celery_app_test.task(name="test.ping", bind=False)
def ping_task() -> str:
    """
    Простая задача для проверки готовности worker.

    Не импортирует сервисы, не использует БД, просто возвращает "pong".
    Используется в pytest fixture для ожидания готовности worker.

    Returns:
        "pong" если worker готов обрабатывать задачи
    """
    return "pong"
