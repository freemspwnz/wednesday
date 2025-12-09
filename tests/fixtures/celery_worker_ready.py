import pytest

from tests.common.wait_for_celery import wait_for_celery_worker


@pytest.fixture(scope="session")
def celery_worker_ready() -> None:
    """
    Fixture для ожидания готовности Celery worker перед запуском E2E тестов.

    Автоматически вызывается для всех тестов (autouse=True), которые используют
    тестовое Celery окружение.
    """
    wait_for_celery_worker()
