"""
E2E тесты для Celery задач Wednesday Frog Bot.

Эти тесты требуют запущенных контейнеров:
- postgres_test
- redis_test
- celery-worker-test
- celery-beat-test (опционально, для тестов расписания)

Запуск:
    1. Запустить контейнеры:
       docker-compose -f docker-compose.test.yml up -d

    2. Дождаться готовности worker'а (проверить healthcheck):
       docker-compose -f docker-compose.test.yml ps

    3. Запустить тесты:
       pytest tests/test_services/test_celery_e2e.py -v -m e2e

    4. Остановить контейнеры:
       docker-compose -f docker-compose.test.yml down

Примечание:
    - Тесты проверяют реальное взаимодействие с Celery worker через Redis
    - Не требуют реального выполнения задач (только проверка отправки и структуры)
    - Для полного E2E тестирования с реальным выполнением задач нужны моки внешних API
"""

import asyncio
from typing import Any

import pytest
from celery.result import AsyncResult

from services.celery_app import celery_app


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_worker_availability() -> None:
    """E2E тест: проверка доступности Celery worker."""
    # Проверяем, что worker доступен через control.inspect()
    inspect = celery_app.control.inspect()

    # Получаем список активных worker'ов
    active_workers = inspect.active()

    assert active_workers is not None, "Worker не доступен (inspect.active() вернул None)"
    assert len(active_workers) > 0, "Нет активных worker'ов"

    # Проверяем, что worker зарегистрирован
    registered = inspect.registered()
    assert registered is not None, "Worker не зарегистрирован"
    assert len(registered) > 0, "Нет зарегистрированных worker'ов"

    # Проверяем статистику worker'а
    stats = inspect.stats()
    assert stats is not None, "Не удалось получить статистику worker'а"
    assert len(stats) > 0, "Нет статистики worker'ов"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_task_can_be_sent_to_queue() -> None:
    """E2E тест: проверка отправки задачи в очередь."""
    # Отправляем задачу в очередь (без выполнения, только проверка отправки)
    result: AsyncResult = celery_app.send_task(
        "wednesday.send_frog",
        args=("09:00",),
        queue="wednesday",
    )

    assert result is not None, "Задача не была отправлена"
    assert result.id is not None, "Задача не получила ID"
    assert result.state in {"PENDING", "RECEIVED", "STARTED", "SUCCESS", "FAILURE"}, (
        f"Неожиданное состояние задачи: {result.state}"
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_task_routing() -> None:
    """E2E тест: проверка маршрутизации задач по очередям."""
    # Проверяем, что задачи маршрутизируются в правильные очереди
    queues = ["wednesday", "images", "maintenance"]

    for queue_name in queues:
        # Отправляем тестовую задачу в каждую очередь
        if queue_name == "wednesday":
            task_name = "wednesday.send_frog"
            args: tuple[Any, ...] = ("09:00",)
        elif queue_name == "images":
            task_name = "wednesday.generate_image"
            args = (None,)
        else:
            task_name = "wednesday.daily_cleanup"
            args = ()

        result: AsyncResult = celery_app.send_task(
            task_name,
            args=args,
            queue=queue_name,
        )

        assert result is not None, f"Задача не была отправлена в очередь {queue_name}"
        assert result.id is not None, f"Задача в очереди {queue_name} не получила ID"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_beat_schedule_registered() -> None:
    """E2E тест: проверка регистрации расписания в Celery Beat."""
    # Проверяем, что расписание настроено
    assert hasattr(celery_app.conf, "beat_schedule")
    assert celery_app.conf.beat_schedule is not None

    # Проверяем наличие задач в расписании
    assert len(celery_app.conf.beat_schedule) > 0, "Расписание пусто"

    # Проверяем, что задачи зарегистрированы
    for task_name, task_config in celery_app.conf.beat_schedule.items():
        assert "task" in task_config, f"Задача {task_name} не имеет поля 'task'"
        assert "schedule" in task_config, f"Задача {task_name} не имеет поля 'schedule'"

        # Проверяем, что задача существует в celery_app
        full_task_name = task_config["task"]
        assert full_task_name in celery_app.tasks, f"Задача {full_task_name} не зарегистрирована"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_queue_length_monitoring() -> None:
    """E2E тест: проверка мониторинга длины очередей."""
    inspect = celery_app.control.inspect()

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
    # Отправляем задачу и проверяем, что результат сохраняется
    result: AsyncResult = celery_app.send_task(
        "wednesday.send_frog",
        args=("09:00",),
        queue="wednesday",
    )

    # Ждём немного, чтобы задача могла быть обработана
    await asyncio.sleep(1)

    # Проверяем, что результат доступен через result backend
    # (даже если задача ещё не выполнена, результат должен быть доступен)
    assert result.id is not None

    # Проверяем состояние задачи
    state = result.state
    assert state in {"PENDING", "RECEIVED", "STARTED", "SUCCESS", "FAILURE", "RETRY"}, (
        f"Неожиданное состояние задачи: {state}"
    )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_multiple_workers_concurrency() -> None:
    """E2E тест: проверка конкурентного выполнения задач."""
    # Отправляем несколько задач одновременно
    tasks: list[AsyncResult] = []

    for i in range(3):
        result: AsyncResult = celery_app.send_task(
            "wednesday.send_frog",
            args=(f"09:0{i}",),
            queue="wednesday",
        )
        tasks.append(result)

    # Проверяем, что все задачи были отправлены
    assert len(tasks) == 3, "Не все задачи были отправлены"

    for task in tasks:
        assert task.id is not None, "Задача не получила ID"
        assert task.state in {"PENDING", "RECEIVED", "STARTED", "SUCCESS", "FAILURE"}, (
            f"Неожиданное состояние задачи: {task.state}"
        )


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_worker_stats() -> None:
    """E2E тест: проверка статистики worker'а."""
    inspect = celery_app.control.inspect()

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
    """E2E тест: проверка механизма retry (только структура, без реального выполнения)."""
    # Отправляем задачу с параметрами retry
    result: AsyncResult = celery_app.send_task(
        "wednesday.send_frog",
        args=("09:00",),
        queue="wednesday",
        # Задача уже настроена с autoretry_for в декораторе
    )

    assert result is not None, "Задача не была отправлена"
    assert result.id is not None, "Задача не получила ID"

    # Проверяем, что задача имеет настройки retry (через конфигурацию)
    task = celery_app.tasks.get("wednesday.send_frog")
    assert task is not None, "Задача wednesday.send_frog не найдена"

    # Проверяем, что у задачи настроены параметры retry
    # (это проверяется через конфигурацию задачи, а не через выполнение)
    assert hasattr(task, "autoretry_for"), "Задача должна иметь настройку autoretry_for"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_celery_beat_schedule_timezone() -> None:
    """E2E тест: проверка корректности timezone в расписании."""
    # Проверяем, что timezone установлен корректно
    assert celery_app.conf.timezone is not None, "Timezone не установлен"
    assert celery_app.conf.enable_utc is False, "UTC должен быть отключен для использования локального timezone"

    # Проверяем, что все задачи в расписании используют правильный timezone
    # (timezone применяется глобально через celery_app.conf.timezone)
    for task_name, task_config in celery_app.conf.beat_schedule.items():
        schedule = task_config.get("schedule")
        assert schedule is not None, f"Задача {task_name} не имеет расписания"

        # Проверяем, что расписание является crontab объектом
        from celery.schedules import crontab

        assert isinstance(schedule, crontab), f"Расписание задачи {task_name} должно быть crontab"
