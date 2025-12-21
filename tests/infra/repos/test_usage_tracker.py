from datetime import datetime
from typing import Any

import pytest

from infra.repos.usage_tracker import UsageTracker

# Константы для тестов
TEST_QUOTA_50 = 50
TEST_THRESHOLD_20 = 20
TEST_QUOTA_10 = 10
TEST_THRESHOLD_5 = 5
TEST_INCREMENT_2 = 2
TEST_INCREMENT_3 = 3
TEST_TOTAL_5 = 5
TEST_QUOTA_15 = 15
TEST_THRESHOLD_10 = 10
TEST_TOTAL_7 = 7

pytestmark = [
    pytest.mark.integration,
    pytest.mark.db,
    pytest.mark.usefixtures("_setup_test_postgres"),
]


def test_usage_tracker_initial_save(async_postgres_pool: Any) -> None:
    tracker = UsageTracker(
        pool=async_postgres_pool,
        monthly_quota=TEST_QUOTA_50,
        frog_threshold=TEST_THRESHOLD_20,
    )

    assert tracker.monthly_quota == TEST_QUOTA_50
    assert tracker.frog_threshold == TEST_THRESHOLD_20


@pytest.mark.asyncio
async def test_usage_tracker_increment_and_limits(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    tracker = UsageTracker(
        pool=async_postgres_pool,
        monthly_quota=TEST_QUOTA_10,
        frog_threshold=TEST_THRESHOLD_5,
    )
    when = datetime(2025, 1, 1)

    await tracker.increment(TEST_INCREMENT_2, when=when)
    assert await tracker.get_month_total(when=when) == TEST_INCREMENT_2
    assert await tracker.can_use_frog(when=when) is True

    await tracker.increment(TEST_INCREMENT_3, when=when)
    assert await tracker.get_month_total(when=when) == TEST_TOTAL_5
    assert await tracker.can_use_frog(when=when) is False


@pytest.mark.asyncio
async def test_usage_tracker_threshold_and_totals(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    tracker = UsageTracker(
        pool=async_postgres_pool,
        monthly_quota=TEST_QUOTA_15,
        frog_threshold=TEST_THRESHOLD_10,
    )
    when = datetime(2025, 2, 1)

    await tracker.set_month_total(TEST_TOTAL_7, when=when)
    total, threshold, quota = await tracker.get_limits_info(when=when)
    assert total == TEST_TOTAL_7
    assert threshold == tracker.frog_threshold
    assert quota == tracker.monthly_quota

    new_threshold = await tracker.set_frog_threshold(25)
    assert new_threshold == tracker.monthly_quota  # ограничено квотой


@pytest.mark.asyncio
async def test_usage_tracker_increment_with_connection(
    cleanup_tables: Any,
    async_postgres_pool: Any,
) -> None:
    """Тест increment с переданным соединением (в транзакции)."""
    from infra.database.database_unit_of_work import DatabaseUnitOfWork

    tracker = UsageTracker(
        pool=async_postgres_pool,
        monthly_quota=TEST_QUOTA_10,
        frog_threshold=TEST_THRESHOLD_5,
    )
    when = datetime(2025, 1, 1)

    # Используем DatabaseUnitOfWork для транзакции
    from unittest.mock import MagicMock

    mock_logger = MagicMock()
    mock_logger.bind.return_value = mock_logger
    async with DatabaseUnitOfWork(pool=async_postgres_pool, logger=mock_logger) as uow:
        connection = uow.connection
        result = await tracker.increment(TEST_INCREMENT_2, when=when, connection=connection)

    # После коммита транзакции проверяем, что значение сохранилось
    assert result == TEST_INCREMENT_2
    assert await tracker.get_month_total(when=when) == TEST_INCREMENT_2
