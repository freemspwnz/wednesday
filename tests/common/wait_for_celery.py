"""
Общая утилита для ожидания готовности Celery worker в E2E тестах.

Проверяет только поведение:
- worker может принять и успешно выполнить задачу test.ping в очереди test_main.
"""

from celery.result import AsyncResult
from tenacity import retry, stop_after_delay, wait_exponential

from tests.common.celery_app_test import (
    CeleryTestQueues,
    celery_app_test,
    ensure_queues_consumed,
    generate_celery_test_queues,
)


@retry(
    stop=stop_after_delay(30),  # Максимум 30 секунд на полное ожидание готовности
    wait=wait_exponential(multiplier=1.0, min=0.5, max=5.0),  # Экспоненциальный backoff: 0.5s, 1s, 2s, 4s, 5s
    reraise=True,
)
def wait_for_celery_worker(queues: CeleryTestQueues | None = None) -> CeleryTestQueues:
    """
    Ожидает готовности Celery worker для обработки задач с retry/backoff.

    Использует экспоненциальный backoff для повторных попыток при недоступности worker.
    Делает простую проверку:
    - отправляет test.ping в динамическую очередь и ждёт "pong" с таймаутом 5 секунд.

    Raises:
        TimeoutError: Если worker не готов после всех попыток retry.
    """
    queues = queues or generate_celery_test_queues()
    ensure_queues_consumed(queues)

    result: AsyncResult = celery_app_test.send_task(
        "test.ping",
        queue=queues.main,
    )

    try:
        # Снижаем таймаут до 5 секунд для быстрого обнаружения проблем
        ping_result = result.get(timeout=5)
        if ping_result != "pong":
            raise TimeoutError(f"Неожиданный результат test.ping: {ping_result}")
    except Exception as e:
        raise TimeoutError(
            f"Celery worker не готов: test.ping задача не выполнилась. "
            f"Ошибка: {e}. Проверьте логи контейнера celery-worker-test."
        ) from e

    return queues
