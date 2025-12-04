"""
Общая утилита для ожидания готовности Celery worker в E2E тестах.

Проверяет только поведение:
- worker может принять и успешно выполнить задачу test.ping в очереди test_main.
"""

from celery.result import AsyncResult
from tenacity import retry, stop_after_delay, wait_exponential

from services.celery_app_test import celery_app_test


@retry(
    stop=stop_after_delay(30),  # Максимум 30 секунд на полное ожидание готовности
    wait=wait_exponential(multiplier=1, min=1, max=5),  # Экспоненциальная задержка между попытками
    reraise=True,
)
def wait_for_celery_worker() -> None:
    """
    Ожидает готовности Celery worker для обработки задач.

    Делает одну простую проверку:
    - отправляет test.ping в очередь test_main и ждёт "pong".
    """
    result: AsyncResult = celery_app_test.send_task(
        "test.ping",
        queue="test_main",
    )

    try:
        ping_result = result.get(timeout=10)
        if ping_result != "pong":
            raise TimeoutError(f"Неожиданный результат test.ping: {ping_result}")
    except Exception as e:
        raise TimeoutError(
            f"Celery worker не готов: test.ping задача не выполнилась. "
            f"Ошибка: {e}. Проверьте логи контейнера celery-worker-test."
        ) from e
