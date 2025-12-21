"""
Реестр отправленных сообщений по тайм-слотам и чатам на базе PostgreSQL.

Ранее данные хранились в JSON-файле `data/dispatch_registry.json`, теперь
используется таблица `dispatch_registry`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import asyncpg

from infra.database.postgres_client import get_postgres_pool
from infra.logging.logger import get_logger, log_all_methods


@log_all_methods()
class DispatchRegistry:
    """Реестр отправленных сообщений по тайм-слотам и чатам.

    Хранит информацию о том, какие сообщения уже были отправлены
    в определённые временные слоты и чаты для предотвращения дубликатов.
    """

    def __init__(
        self,
        pool: asyncpg.Pool,
        retention_days: int = 7,
    ) -> None:
        """Инициализирует реестр отправленных сообщений.

        Args:
            pool: Пул подключений PostgreSQL.
            retention_days: Количество дней хранения записей в реестре (по умолчанию 7).
        """
        self._pool = pool
        self.logger = get_logger(__name__)
        self.retention_days = retention_days

    @staticmethod
    def _key(slot_date: str, slot_time: str, chat_id: int) -> str:
        """Формирует ключ для записи в реестре.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_id: Идентификатор чата.

        Returns:
            Строковый ключ в формате "{slot_date}_{slot_time}:{chat_id}".
        """
        return f"{slot_date}_{slot_time}:{chat_id}"

    async def is_dispatched(self, slot_date: str, slot_time: str, chat_id: int) -> bool:
        """Проверяет, было ли уже отправлено сообщение в указанный слот и чат.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_id: Идентификатор чата для проверки.

        Returns:
            True если сообщение уже было отправлено, False иначе.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        key = self._key(slot_date, slot_time, chat_id)
        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "SELECT 1 FROM dispatch_registry WHERE key = $1;",
                    key,
                )
                return row is not None
            except Exception as exc:
                self.logger.error(
                    f"Ошибка при проверке dispatch_registry (key={key}) в Postgres: {exc}",
                )
                raise

    async def mark_dispatched(
        self,
        slot_date: str,
        slot_time: str,
        chat_id: int,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Помечает сочетание (дата, время, чат) как уже отправленное.

        Создаёт запись в реестре, если её ещё нет. При конфликте ключа
        (дубликат) операция игнорируется.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_id: Идентификатор чата для пометки.
            connection: Соединение БД для использования в транзакции (опционально).

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        from datetime import date as date_type

        key = self._key(slot_date, slot_time, chat_id)
        # Преобразуем строку в date объект для asyncpg
        slot_date_obj = date_type.fromisoformat(slot_date) if isinstance(slot_date, str) else slot_date

        # Используем переданное соединение или получаем новое
        if connection is not None:
            try:
                await connection.execute(
                    """
                    INSERT INTO dispatch_registry (key, slot_date, slot_time, chat_id, created_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (key) DO NOTHING;
                    """,
                    key,
                    slot_date_obj,
                    slot_time,
                    int(chat_id),
                )
            except Exception as exc:
                self.logger.error(
                    f"Ошибка при записи dispatch_registry (key={key}) в Postgres: {exc}",
                )
                raise
        else:
            pool = get_postgres_pool()
            async with pool.acquire() as conn:
                try:
                    await conn.execute(
                        """
                        INSERT INTO dispatch_registry (key, slot_date, slot_time, chat_id, created_at)
                        VALUES ($1, $2, $3, $4, NOW())
                        ON CONFLICT (key) DO NOTHING;
                        """,
                        key,
                        slot_date_obj,
                        slot_time,
                        int(chat_id),
                    )
                except Exception as exc:
                    self.logger.error(
                        f"Ошибка при записи dispatch_registry (key={key}) в Postgres: {exc}",
                    )
                    raise

    async def cleanup_old(self) -> None:
        """Удаляет старые записи реестра старше retention_days.

        Удаляет все записи, у которых created_at меньше текущей даты
        минус retention_days дней.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        cutoff_dt = datetime.utcnow() - timedelta(days=self.retention_days)
        async with self._pool.acquire() as conn:
            try:
                await conn.execute(
                    "DELETE FROM dispatch_registry WHERE created_at < $1;",
                    cutoff_dt,
                )
                message = (
                    "Очистка dispatch_registry старше "
                    f"{self.retention_days} дней выполнена "
                    f"(cutoff={cutoff_dt.isoformat()})"
                )
                self.logger.info(message)
            except Exception as exc:
                self.logger.error(f"Ошибка при очистке dispatch_registry в Postgres: {exc}")
                raise
