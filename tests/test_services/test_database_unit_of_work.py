"""Unit-тесты для DatabaseUnitOfWork."""

from __future__ import annotations

from typing import Any

import pytest

from services.infrastructure.database_unit_of_work import DatabaseUnitOfWork

pytestmark = [
    pytest.mark.integration,
    pytest.mark.db,
    pytest.mark.usefixtures("_setup_test_postgres"),
]


@pytest.mark.asyncio
async def test_database_unit_of_work_context_manager_success(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    """Тест успешного коммита транзакции через context manager."""
    uow = DatabaseUnitOfWork(pool=async_postgres_pool)

    async with uow:
        connection = uow.connection
        # Выполняем простую операцию
        await connection.execute("CREATE TABLE IF NOT EXISTS test_table (id SERIAL PRIMARY KEY, value TEXT);")
        await connection.execute("INSERT INTO test_table (value) VALUES ($1);", "test_value")

    # После выхода из context manager транзакция должна быть закоммичена
    # Проверяем, что данные сохранились
    async with async_postgres_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM test_table WHERE value = $1;", "test_value")
        assert row is not None
        assert row["value"] == "test_value"


@pytest.mark.asyncio
async def test_database_unit_of_work_context_manager_rollback(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    """Тест отката транзакции при ошибке через context manager."""
    uow = DatabaseUnitOfWork(pool=async_postgres_pool)

    try:
        async with uow:
            connection = uow.connection
            await connection.execute("CREATE TABLE IF NOT EXISTS test_table (id SERIAL PRIMARY KEY, value TEXT);")
            await connection.execute("INSERT INTO test_table (value) VALUES ($1);", "test_value")
            # Вызываем ошибку для отката
            raise ValueError("Test error")
    except ValueError:
        pass

    # После ошибки транзакция должна быть откатана
    # Проверяем, что данные не сохранились
    async with async_postgres_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM test_table WHERE value = $1;", "test_value")
        assert row is None


@pytest.mark.asyncio
async def test_database_unit_of_work_manual_commit(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    """Тест ручного управления транзакцией."""
    uow = DatabaseUnitOfWork(pool=async_postgres_pool)

    await uow.begin()
    connection = uow.connection
    await connection.execute("CREATE TABLE IF NOT EXISTS test_table (id SERIAL PRIMARY KEY, value TEXT);")
    await connection.execute("INSERT INTO test_table (value) VALUES ($1);", "test_value")
    await uow.commit()

    # Проверяем, что данные сохранились
    async with async_postgres_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM test_table WHERE value = $1;", "test_value")
        assert row is not None
        assert row["value"] == "test_value"


@pytest.mark.asyncio
async def test_database_unit_of_work_manual_rollback(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    """Тест ручного отката транзакции."""
    uow = DatabaseUnitOfWork(pool=async_postgres_pool)

    await uow.begin()
    connection = uow.connection
    await connection.execute("CREATE TABLE IF NOT EXISTS test_table (id SERIAL PRIMARY KEY, value TEXT);")
    await connection.execute("INSERT INTO test_table (value) VALUES ($1);", "test_value")
    await uow.rollback()

    # Проверяем, что данные не сохранились
    async with async_postgres_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM test_table WHERE value = $1;", "test_value")
        assert row is None


@pytest.mark.asyncio
async def test_database_unit_of_work_double_begin_error(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    """Тест ошибки при попытке начать транзакцию дважды."""
    uow = DatabaseUnitOfWork(pool=async_postgres_pool)

    await uow.begin()
    # Попытка начать транзакцию второй раз должна вызвать ошибку
    with pytest.raises(RuntimeError, match="Транзакция уже начата"):
        await uow.begin()

    await uow.rollback()


@pytest.mark.asyncio
async def test_database_unit_of_work_connection_property(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    """Тест получения соединения через property."""
    uow = DatabaseUnitOfWork(pool=async_postgres_pool)

    # До начала транзакции property должна вызывать ошибку
    with pytest.raises(RuntimeError, match="Транзакция не начата"):
        _ = uow.connection

    async with uow:
        connection = uow.connection
        assert connection is not None
        # Проверяем, что соединение работает
        result = await connection.fetchval("SELECT 1;")
        assert result == 1


@pytest.mark.asyncio
async def test_database_unit_of_work_get_connection(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    """Тест получения соединения через get_connection()."""
    uow = DatabaseUnitOfWork(pool=async_postgres_pool)

    # До начала транзакции должно возвращать None
    assert uow.get_connection() is None

    async with uow:
        connection = uow.get_connection()
        assert connection is not None
        # Проверяем, что соединение работает
        result = await connection.fetchval("SELECT 1;")
        assert result == 1

    # После завершения транзакции должно возвращать None
    assert uow.get_connection() is None
