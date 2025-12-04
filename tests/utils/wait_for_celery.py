"""
Утилита для ожидания готовности Celery worker в E2E тестах.

Использует test.ping задачу для проверки готовности worker без импорта сервисов/БД.

⚠️ КРИТИЧНО: Функция синхронная (не async), т.к. Celery API синхронный.
Смешивание asyncio.to_thread с Celery sync API приводит к race conditions и зависаниям.
"""

import pytest
from celery.result import AsyncResult
from tenacity import retry, stop_after_delay, wait_exponential

from services.celery_app_test import celery_app_test


@retry(
    stop=stop_after_delay(30),  # Максимум 30 секунд
    wait=wait_exponential(multiplier=1, min=1, max=5),  # Экспоненциальная задержка
    reraise=True,
)
def wait_for_celery_worker() -> None:
    """
    Ожидает готовности Celery worker для обработки задач.

    ⚠️ СИНХРОННАЯ функция (не async) - Celery API синхронный.

    Проверяет:
    1. Доступность Redis (broker) - синхронная проверка
    2. Регистрацию очередей worker через inspect().active_queues()
    3. Способность worker обработать test.ping задачу

    Использует tenacity для retry логики с экспоненциальной задержкой.

    Raises:
        TimeoutError: Если worker не готов в течение 30 секунд
        ConnectionError: Если Redis недоступен
    """
    # Проверка 1: Redis доступен (синхронная проверка через redis-py)
    try:
        import redis

        from utils.config import config

        # Используем синхронный redis клиент для проверки
        redis_client = redis.Redis(
            host=config.redis_host,
            port=config.redis_port,
            db=config.redis_db,
            password=config.redis_password if config.redis_password else None,
            socket_connect_timeout=2,
        )
        redis_client.ping()
        redis_client.close()
    except Exception as e:
        raise ConnectionError(f"Redis недоступен: {e}") from e

    # Проверка 2: Worker зарегистрировал очереди
    # Это гарантирует, что worker не просто запущен, но и готов обрабатывать задачи
    inspect = celery_app_test.control.inspect(timeout=2)
    active_queues = inspect.active_queues()

    if not active_queues:
        raise TimeoutError("Celery worker не зарегистрировал очереди. Проверьте логи контейнера celery-worker-test.")

    # Проверяем, что worker слушает тестовую очередь test_main
    test_main_found = False
    for _worker_name, queues in active_queues.items():
        for queue_info in queues:
            if queue_info.get("name") == "test_main":
                test_main_found = True
                break
        if test_main_found:
            break

    if not test_main_found:
        raise TimeoutError(
            "Celery worker не слушает очередь test_main. Проверьте команду запуска worker в docker-compose.test.yml."
        )

    # Проверка 3: Worker может обработать test.ping задачу
    # Используем тестовую очередь test_main
    result: AsyncResult = celery_app_test.send_task(
        "test.ping",
        queue="test_main",
    )

    # Ждём результат с таймаутом (синхронно, без asyncio.to_thread)
    try:
        ping_result = result.get(timeout=10)
        if ping_result != "pong":
            raise ValueError(f"Неожиданный результат test.ping: {ping_result}")
    except Exception as e:
        raise TimeoutError(
            f"Celery worker не готов: test.ping задача не выполнилась. "
            f"Ошибка: {e}. Проверьте логи контейнера celery-worker-test."
        ) from e


@pytest.fixture(scope="session", autouse=True)
def celery_worker_ready() -> None:
    """
    Fixture для ожидания готовности Celery worker перед запуском E2E тестов.

    ⚠️ СИНХРОННАЯ fixture (не async) - wait_for_celery_worker синхронная.

    Автоматически вызывается для всех E2E тестов (autouse=True).
    """
    wait_for_celery_worker()
