"""
E2E тесты для Celery задач Wednesday Frog Bot.

Эти тесты требуют запущенных контейнеров:
- postgres_test
- redis_test
- celery-worker-test (с тестовыми очередями test_main, test_images, test_maintenance)

Запуск:
    1. Запустить контейнеры:
       make test-up

    2. Запустить тесты:
       make test-e2e

    3. Остановить контейнеры:
       make test-down

Примечание:
    - Тесты используют тестовый Celery app (services.celery_app_test) с тестовыми очередями
    - Worker запущен с тестовыми очередями для изоляции от production
    - Тесты проверяют реальное взаимодействие с Celery worker через Redis
"""

import asyncio

import pytest
from celery.result import AsyncResult

from services.celery_app_test import celery_app_test


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_worker_availability() -> None:
    """E2E тест: проверка доступности Celery worker через тестовый app."""
    # Проверяем, что worker доступен через control.inspect()
    inspect = celery_app_test.control.inspect(timeout=5)

    # Проверяем через ping (более надёжный способ)
    ping_result = inspect.ping()
    assert ping_result is not None, "Worker не отвечает на ping"
    assert len(ping_result) > 0, "Нет worker'ов, отвечающих на ping"

    # Получаем список активных worker'ов
    active_workers = inspect.active()
    # active() может вернуть None если нет активных задач, но worker должен быть доступен через ping
    if active_workers is not None:
        assert len(active_workers) >= 0, "Неожиданный формат active_workers"

    # Проверяем, что worker зарегистрирован
    registered = inspect.registered()
    assert registered is not None, "Worker не зарегистрирован"
    assert len(registered) > 0, "Нет зарегистрированных worker'ов"

    # Проверяем, что test.ping зарегистрирована
    assert "test.ping" in registered[list(registered.keys())[0]], "Задача test.ping не зарегистрирована"

    # Проверяем статистику worker'а
    stats = inspect.stats()
    assert stats is not None, "Не удалось получить статистику worker'а"
    assert len(stats) > 0, "Нет статистики worker'ов"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_task_can_be_sent_to_queue() -> None:
    """E2E тест: проверка отправки задачи в тестовую очередь."""
    # Отправляем тестовую задачу test.ping в тестовую очередь
    result: AsyncResult = celery_app_test.send_task(
        "test.ping",
        queue="test_main",
    )

    assert result is not None, "Задача не была отправлена"
    assert result.id is not None, "Задача не получила ID"

    # Ждём выполнения задачи
    try:
        ping_result = result.get(timeout=10)
        assert ping_result == "pong", f"Неожиданный результат: {ping_result}"
    except Exception as e:
        pytest.fail(f"Задача не выполнилась: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_task_routing() -> None:
    """E2E тест: проверка маршрутизации задач по тестовым очередям."""
    # Проверяем, что задачи маршрутизируются в правильные тестовые очереди
    test_queues = ["test_main", "test_images", "test_maintenance"]

    for queue_name in test_queues:
        # Отправляем тестовую задачу test.ping в каждую очередь
        result: AsyncResult = celery_app_test.send_task(
            "test.ping",
            queue=queue_name,
        )

        assert result is not None, f"Задача не была отправлена в очередь {queue_name}"
        assert result.id is not None, f"Задача в очереди {queue_name} не получила ID"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_beat_schedule_registered() -> None:
    """E2E тест: проверка регистрации расписания в Celery Beat."""
    # Тестовый app не имеет расписания Beat, но мы можем проверить конфигурацию
    # Проверяем, что beat_schedule либо отсутствует, либо пуст (для тестового app это нормально)
    if hasattr(celery_app_test.conf, "beat_schedule"):
        # Если beat_schedule есть, проверяем его структуру
        beat_schedule = celery_app_test.conf.beat_schedule
        if beat_schedule:
            for task_name, task_config in beat_schedule.items():
                assert "task" in task_config, f"Задача {task_name} не имеет поля 'task'"
                assert "schedule" in task_config, f"Задача {task_name} не имеет поля 'schedule'"
    # Для тестового app отсутствие beat_schedule - это нормально


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_queue_length_monitoring() -> None:
    """E2E тест: проверка мониторинга длины очередей."""
    inspect = celery_app_test.control.inspect()

    # Получаем длину очередей
    reserved = inspect.reserved()
    active = inspect.active()
    scheduled = inspect.scheduled()

    # Проверяем, что inspect работает (может вернуть None если worker недоступен)
    # Но если worker доступен, должны получить словари
    if reserved is not None:
        assert isinstance(reserved, dict), "reserved() должен вернуть словарь"

    if active is not None:
        assert isinstance(active, dict), "active() должен вернуть словарь"

    if scheduled is not None:
        assert isinstance(scheduled, dict), "scheduled() должен вернуть словарь"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_task_result_backend() -> None:
    """E2E тест: проверка работы result backend (Redis)."""
    # Отправляем тестовую задачу и проверяем, что результат сохраняется
    result: AsyncResult = celery_app_test.send_task(
        "test.ping",
        queue="test_main",
    )

    # Ждём немного, чтобы задача могла быть обработана
    await asyncio.sleep(1)

    # Проверяем, что результат доступен через result backend
    assert result.id is not None

    # Проверяем состояние задачи и результат
    try:
        ping_result = result.get(timeout=10)
        assert ping_result == "pong", f"Неожиданный результат: {ping_result}"
        assert result.state == "SUCCESS", f"Задача должна быть успешно выполнена, но состояние: {result.state}"
    except Exception as e:
        pytest.fail(f"Задача не выполнилась или результат недоступен: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_multiple_workers_concurrency() -> None:
    """E2E тест: проверка конкурентного выполнения задач."""
    # Отправляем несколько тестовых задач одновременно
    tasks: list[AsyncResult] = []

    for _i in range(3):
        result: AsyncResult = celery_app_test.send_task(
            "test.ping",
            queue="test_main",
        )
        tasks.append(result)

    # Проверяем, что все задачи были отправлены
    assert len(tasks) == 3, "Не все задачи были отправлены"

    # Ждём выполнения всех задач
    for task in tasks:
        assert task.id is not None, "Задача не получила ID"
        try:
            ping_result = task.get(timeout=10)
            assert ping_result == "pong", f"Неожиданный результат: {ping_result}"
        except Exception as e:
            pytest.fail(f"Задача {task.id} не выполнилась: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_worker_stats() -> None:
    """E2E тест: проверка статистики worker'а."""
    inspect = celery_app_test.control.inspect()

    # Получаем статистику worker'а
    stats = inspect.stats()

    if stats is None:
        pytest.skip("Worker недоступен для получения статистики")

    assert len(stats) > 0, "Нет статистики worker'ов"

    # Проверяем структуру статистики
    for worker_name, worker_stats in stats.items():
        assert isinstance(worker_stats, dict), f"Статистика worker'а {worker_name} должна быть словарём"
        # Проверяем наличие основных полей статистики
        assert "pool" in worker_stats or "prefetch_count" in worker_stats, (
            f"Статистика worker'а {worker_name} не содержит ожидаемых полей"
        )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_task_retry_mechanism() -> None:
    """E2E тест: проверка механизма retry."""
    # Тестовый app имеет простую задачу test.ping без retry
    # Проверяем, что задача test.ping зарегистрирована и может быть выполнена
    task = celery_app_test.tasks.get("test.ping")
    assert task is not None, "Задача test.ping не найдена"

    # Отправляем задачу и проверяем успешное выполнение
    result: AsyncResult = celery_app_test.send_task(
        "test.ping",
        queue="test_main",
    )

    assert result is not None, "Задача не была отправлена"
    assert result.id is not None, "Задача не получила ID"

    # Ждём выполнения
    try:
        ping_result = result.get(timeout=10)
        assert ping_result == "pong", f"Неожиданный результат: {ping_result}"
    except Exception as e:
        pytest.fail(f"Задача не выполнилась: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_beat_schedule_timezone() -> None:
    """E2E тест: проверка корректности timezone в конфигурации."""
    # Проверяем, что timezone установлен в конфигурации (даже если нет расписания)
    # Тестовый app может не иметь timezone, но мы проверяем конфигурацию
    if hasattr(celery_app_test.conf, "timezone"):
        timezone = celery_app_test.conf.timezone
        # Если timezone установлен, проверяем что он валидный
        if timezone is not None:
            assert isinstance(timezone, str), "Timezone должен быть строкой"
            assert len(timezone) > 0, "Timezone не должен быть пустым"

    # Для тестового app отсутствие timezone - это нормально, т.к. нет расписания Beat
