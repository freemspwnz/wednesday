"""
Базовый поведенческий e2e‑набор для тестового Celery app.

Проверяет:
- возможность выполнить test.ping и получить "pong";
- работу result backend;
- конкурентную обработку нескольких задач.
"""

import pytest
from celery.result import AsyncResult

from services.celery_app_test import celery_app_test


@pytest.mark.e2e
def test_celery_ping_basic() -> None:
    """Отправляем test.ping в test_main и ждём pong."""
    result: AsyncResult = celery_app_test.send_task(
        "test.ping",
        queue="test_main",
    )

    ping_result = result.get(timeout=10)
    assert ping_result == "pong"


@pytest.mark.e2e
def test_celery_result_backend() -> None:
    """Проверяем, что результат задачи доступен через result backend."""
    result: AsyncResult = celery_app_test.send_task(
        "test.ping",
        queue="test_main",
    )

    assert result.id is not None

    ping_result = result.get(timeout=10)
    assert ping_result == "pong"
    assert result.state == "SUCCESS"


@pytest.mark.e2e
def test_celery_concurrent_tasks() -> None:
    """Отправляем несколько задач одновременно и убеждаемся, что все завершаются успешно."""
    tasks: list[AsyncResult] = []

    for _ in range(3):
        task: AsyncResult = celery_app_test.send_task(
            "test.ping",
            queue="test_main",
        )
        tasks.append(task)

    assert len(tasks) == 3

    for task in tasks:
        assert task.id is not None
        ping_result = task.get(timeout=10)
        assert ping_result == "pong"
