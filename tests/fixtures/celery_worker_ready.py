import pytest

from tests.common.celery_app_test import (
    CeleryTestQueues,
    drop_test_consumers,
    ensure_queues_consumed,
    generate_celery_test_queues,
)
from tests.common.wait_for_celery import wait_for_celery_worker


@pytest.fixture(scope="function")
def celery_test_queues() -> CeleryTestQueues:
    """Создаёт уникальный набор очередей и подписывает worker на них."""
    queues = generate_celery_test_queues()
    ensure_queues_consumed(queues)
    wait_for_celery_worker(queues)
    try:
        yield queues
    finally:
        drop_test_consumers(queues)


@pytest.fixture(scope="session")
def celery_worker_ready() -> None:
    """
    Fixture для ожидания готовности Celery worker перед запуском E2E тестов.

    Остаётся opt-in через pytest mark, но использует динамическую очередь,
    чтобы проверка готовности не мешала параллельным тестам.
    """
    wait_for_celery_worker()
