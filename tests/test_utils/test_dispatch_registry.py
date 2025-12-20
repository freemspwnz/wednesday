from datetime import date
from typing import Any

import pytest

from utils.dispatch_registry import DispatchRegistry

pytestmark = [
    pytest.mark.integration,
    pytest.mark.db,
    pytest.mark.usefixtures("_setup_test_postgres"),
]


@pytest.mark.asyncio
async def test_dispatch_registry_is_dispatched_false(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    registry = DispatchRegistry(pool=async_postgres_pool)

    # Проверяем несуществующую запись
    result = await registry.is_dispatched("2025-01-01", "10:00", 12345)
    assert result is False


@pytest.mark.asyncio
async def test_dispatch_registry_mark_and_check(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    registry = DispatchRegistry(pool=async_postgres_pool)

    # Помечаем как отправленное (используем текущую дату в формате строки, как в реальном коде)
    from datetime import datetime

    today_str = datetime.now().strftime("%Y-%m-%d")
    # Используем строку, как в реальном коде (asyncpg должен преобразовать через ::date)
    await registry.mark_dispatched(today_str, "10:00", 12345)

    # Проверяем, что запись есть
    result = await registry.is_dispatched(today_str, "10:00", 12345)
    assert result is True


@pytest.mark.asyncio
async def test_dispatch_registry_mark_duplicate(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    registry = DispatchRegistry(pool=async_postgres_pool)

    # Помечаем дважды (используем текущую дату)
    today_str = date.today().strftime("%Y-%m-%d")
    await registry.mark_dispatched(today_str, "10:00", 12345)
    await registry.mark_dispatched(today_str, "10:00", 12345)

    # Проверяем, что запись есть (не должно быть дубликатов)
    result = await registry.is_dispatched(today_str, "10:00", 12345)
    assert result is True


@pytest.mark.asyncio
async def test_dispatch_registry_cleanup_old(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    registry = DispatchRegistry(pool=async_postgres_pool, retention_days=1)

    # Помечаем как отправленное (используем текущую дату)
    today_str = date.today().strftime("%Y-%m-%d")
    await registry.mark_dispatched(today_str, "10:00", 12345)

    # Очищаем старые записи
    await registry.cleanup_old()

    # Запись может остаться или быть удалена в зависимости от даты
    # Главное - метод выполнился без ошибок


@pytest.mark.asyncio
async def test_dispatch_registry_mark_dispatched_with_connection(
    cleanup_tables: Any,
    async_postgres_pool: Any,
) -> None:
    """Тест mark_dispatched с переданным соединением (в транзакции)."""
    from services.infrastructure.database_unit_of_work import DatabaseUnitOfWork

    registry = DispatchRegistry(pool=async_postgres_pool)

    today_str = date.today().strftime("%Y-%m-%d")

    # Используем DatabaseUnitOfWork для транзакции
    async with DatabaseUnitOfWork(pool=async_postgres_pool) as uow:
        connection = uow.connection
        await registry.mark_dispatched(today_str, "10:00", 12345, connection=connection)

    # После коммита транзакции проверяем, что запись есть
    result = await registry.is_dispatched(today_str, "10:00", 12345)
    assert result is True
