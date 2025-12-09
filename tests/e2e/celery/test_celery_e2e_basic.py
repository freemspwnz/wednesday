"""
Базовый поведенческий e2e‑набор для тестового Celery app.

Проверяет:
- возможность выполнить test.ping и получить "pong";
- работу result backend;
- конкурентную обработку нескольких задач.

Использует динамические очереди для изоляции тестов.
"""

import pytest
from celery.result import AsyncResult

from tests.common.celery_app_test import CeleryTestQueues, celery_app_test

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.celery,
    pytest.mark.usefixtures("celery_worker_ready"),
]


def test_celery_ping_basic(celery_test_queues: CeleryTestQueues) -> None:
    """Отправляем test.ping в динамическую очередь и ждём pong."""
    result: AsyncResult = celery_app_test.send_task(
        "test.ping",
        queue=celery_test_queues.main,
    )

    # Снижаем таймаут до 5 секунд для быстрого обнаружения проблем
    ping_result = result.get(timeout=5)
    assert ping_result == "pong"


def test_celery_result_backend(celery_test_queues: CeleryTestQueues) -> None:
    """Проверяем, что результат задачи доступен через result backend."""
    result: AsyncResult = celery_app_test.send_task(
        "test.ping",
        queue=celery_test_queues.main,
    )

    assert result.id is not None

    # Снижаем таймаут до 5 секунд
    ping_result = result.get(timeout=5)
    assert ping_result == "pong"
    assert result.state == "SUCCESS"


def test_celery_concurrent_tasks(celery_test_queues: CeleryTestQueues) -> None:
    """Отправляем несколько задач одновременно и убеждаемся, что все завершаются успешно."""
    tasks: list[AsyncResult] = []

    for _ in range(3):
        task: AsyncResult = celery_app_test.send_task(
            "test.ping",
            queue=celery_test_queues.main,
        )
        tasks.append(task)

    assert len(tasks) == 3

    for task in tasks:
        assert task.id is not None
        # Снижаем таймаут до 5 секунд
        ping_result = task.get(timeout=5)
        assert ping_result == "pong"
