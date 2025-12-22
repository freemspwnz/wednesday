"""Unit-тесты для DatabaseOperationsService."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.database_operations_service import DatabaseOperationsService
from infra.database.database_unit_of_work import DatabaseUnitOfWork
from infra.metrics.metrics import Metrics
from infra.repos.dispatch_registry import DispatchRegistry
from infra.repos.usage_tracker import UsageTracker


def _create_mock_logger() -> MagicMock:
    """Создает mock-логгер для использования в тестах."""
    mock_logger = MagicMock()
    mock_logger.bind.return_value = mock_logger
    return mock_logger


pytestmark = [
    pytest.mark.integration,
    pytest.mark.db,
    pytest.mark.usefixtures("_setup_test_postgres"),
]


@pytest.mark.asyncio
async def test_database_operations_record_dispatch_success(
    cleanup_tables: Any,
    async_postgres_pool: Any,
) -> None:
    """Тест успешной регистрации отправки через DatabaseOperationsService."""
    dispatch_registry = DispatchRegistry(pool=async_postgres_pool)
    usage_tracker = UsageTracker(pool=async_postgres_pool)
    metrics = Metrics(pool=async_postgres_pool)

    def create_unit_of_work() -> DatabaseUnitOfWork:
        return DatabaseUnitOfWork(pool=async_postgres_pool, logger=_create_mock_logger())

    database_operations = DatabaseOperationsService(
        dispatch_registry=dispatch_registry,
        usage_tracker=usage_tracker,
        metrics=metrics,
        unit_of_work_factory=create_unit_of_work,
        logger=_create_mock_logger(),
    )

    slot_date = datetime.now().strftime("%Y-%m-%d")
    slot_time = "10:00"
    chat_id = 12345

    # Регистрируем успешную отправку
    await database_operations.record_dispatch_success(
        slot_date=slot_date,
        slot_time=slot_time,
        chat_id=chat_id,
    )

    # Проверяем, что все операции выполнены атомарно
    # 1. Проверяем dispatch_registry
    is_dispatched = await dispatch_registry.is_dispatched(slot_date, slot_time, chat_id)
    assert is_dispatched is True

    # 2. Проверяем usage_tracker
    total = await usage_tracker.get_month_total()
    assert total == 1

    # 3. Проверяем метрики
    summary = await metrics.get_summary()
    assert summary["dispatches_success"] == 1


@pytest.mark.asyncio
async def test_database_operations_record_dispatch_success_rollback_on_error(
    cleanup_tables: Any,
    async_postgres_pool: Any,
) -> None:
    """Тест отката транзакции при ошибке одной из операций."""
    dispatch_registry = DispatchRegistry(pool=async_postgres_pool)
    usage_tracker = UsageTracker(pool=async_postgres_pool)
    metrics = Metrics(pool=async_postgres_pool)

    # Создаем мок, который будет падать при вызове increment
    class FailingUsageTracker(UsageTracker):
        async def increment(self, count: int = 1, when: datetime | None = None, connection: Any = None) -> int:
            raise RuntimeError("Simulated error")

    failing_usage_tracker = FailingUsageTracker(pool=async_postgres_pool)

    def create_unit_of_work() -> DatabaseUnitOfWork:
        return DatabaseUnitOfWork(pool=async_postgres_pool, logger=_create_mock_logger())

    database_operations = DatabaseOperationsService(
        dispatch_registry=dispatch_registry,
        usage_tracker=failing_usage_tracker,
        metrics=metrics,
        unit_of_work_factory=create_unit_of_work,
        logger=_create_mock_logger(),
    )

    slot_date = datetime.now().strftime("%Y-%m-%d")
    slot_time = "10:00"
    chat_id = 12345

    # Попытка регистрации должна вызвать ошибку и откатить транзакцию
    with pytest.raises(RuntimeError, match="Simulated error"):
        await database_operations.record_dispatch_success(
            slot_date=slot_date,
            slot_time=slot_time,
            chat_id=chat_id,
        )

    # Проверяем, что ничего не сохранилось (транзакция откатилась)
    is_dispatched = await dispatch_registry.is_dispatched(slot_date, slot_time, chat_id)
    assert is_dispatched is False

    # Проверяем, что usage не изменился
    total = await usage_tracker.get_month_total()
    assert total == 0

    # Проверяем, что метрики не изменились
    summary = await metrics.get_summary()
    assert summary["dispatches_success"] == 0


@pytest.mark.asyncio
async def test_database_operations_record_dispatch_failure(
    cleanup_tables: Any,
    async_postgres_pool: Any,
) -> None:
    """Тест регистрации неуспешной отправки."""
    dispatch_registry = DispatchRegistry(pool=async_postgres_pool)
    usage_tracker = UsageTracker(pool=async_postgres_pool)
    metrics = Metrics(pool=async_postgres_pool)

    def create_unit_of_work() -> DatabaseUnitOfWork:
        return DatabaseUnitOfWork(pool=async_postgres_pool, logger=_create_mock_logger())

    database_operations = DatabaseOperationsService(
        dispatch_registry=dispatch_registry,
        usage_tracker=usage_tracker,
        metrics=metrics,
        unit_of_work_factory=create_unit_of_work,
        logger=_create_mock_logger(),
    )

    slot_date = datetime.now().strftime("%Y-%m-%d")
    slot_time = "10:00"
    chat_id = 12345

    # Регистрируем неуспешную отправку
    await database_operations.record_dispatch_failure(
        slot_date=slot_date,
        slot_time=slot_time,
        chat_id=chat_id,
    )

    # Проверяем, что только метрики обновились
    # dispatch_registry и usage не должны измениться
    is_dispatched = await dispatch_registry.is_dispatched(slot_date, slot_time, chat_id)
    assert is_dispatched is False

    total = await usage_tracker.get_month_total()
    assert total == 0

    # Проверяем, что метрики обновились
    summary = await metrics.get_summary()
    assert summary["dispatches_failed"] == 1


@pytest.mark.asyncio
async def test_database_operations_record_dispatch_failure_no_metrics(
    cleanup_tables: Any,
    async_postgres_pool: Any,
) -> None:
    """Тест регистрации неуспешной отправки без метрик."""
    dispatch_registry = DispatchRegistry(pool=async_postgres_pool)
    usage_tracker = UsageTracker(pool=async_postgres_pool)

    def create_unit_of_work() -> DatabaseUnitOfWork:
        return DatabaseUnitOfWork(pool=async_postgres_pool, logger=_create_mock_logger())

    database_operations = DatabaseOperationsService(
        dispatch_registry=dispatch_registry,
        usage_tracker=usage_tracker,
        metrics=None,
        unit_of_work_factory=create_unit_of_work,
        logger=_create_mock_logger(),
    )

    slot_date = datetime.now().strftime("%Y-%m-%d")
    slot_time = "10:00"
    chat_id = 12345

    # Регистрация должна завершиться без ошибок, даже если метрики не заданы
    await database_operations.record_dispatch_failure(
        slot_date=slot_date,
        slot_time=slot_time,
        chat_id=chat_id,
    )

    # Проверяем, что ничего не изменилось
    is_dispatched = await dispatch_registry.is_dispatched(slot_date, slot_time, chat_id)
    assert is_dispatched is False

    total = await usage_tracker.get_month_total()
    assert total == 0
