"""
Реестр отправленных сообщений по тайм-слотам и чатам на базе PostgreSQL.

Ранее данные хранились в JSON-файле `data/dispatch_registry.json`, теперь
используется таблица `dispatch_registry`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import asyncpg

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

    async def are_dispatched_batch(
        self,
        slot_date: str,
        slot_time: str,
        chat_ids: set[int],
    ) -> dict[int, bool]:
        """Проверяет статус отправки для нескольких чатов за один запрос.

        Оптимизированная batch-версия проверки для множества чатов.
        Выполняет один SQL-запрос вместо N отдельных запросов.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_ids: Множество ID чатов для проверки.

        Returns:
            Словарь {chat_id: bool} - True если отправлено, False иначе.
            Если chat_ids пусто, возвращает пустой словарь.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        if not chat_ids:
            return {}

        keys = [self._key(slot_date, slot_time, chat_id) for chat_id in chat_ids]

        async with self._pool.acquire() as conn:
            try:
                # Один batch-запрос для всех ключей
                rows = await conn.fetch(
                    "SELECT key FROM dispatch_registry WHERE key = ANY($1::text[]);",
                    keys,
                )
                dispatched_keys = {row["key"] for row in rows}

                # Формируем результат: для каждого chat_id проверяем наличие ключа
                result = {}
                for chat_id in chat_ids:
                    key = self._key(slot_date, slot_time, chat_id)
                    result[chat_id] = key in dispatched_keys

                return result
            except Exception as exc:
                self.logger.error(
                    f"Ошибка при batch-проверке dispatch_registry в Postgres: {exc}",
                )
                raise

    async def mark_dispatched(
        self,
        slot_date: str,
        slot_time: str,
        chat_id: int,
        connection: asyncpg.Connection,
    ) -> None:
        """Помечает сочетание (дата, время, чат) как уже отправленное.

        Создаёт запись в реестре, если её ещё нет. При конфликте ключа
        (дубликат) операция игнорируется.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_id: Идентификатор чата для пометки.
            connection: Соединение БД для использования в транзакции (обязательно).

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        from datetime import date as date_type

        key = self._key(slot_date, slot_time, chat_id)
        # Преобразуем строку в date объект для asyncpg
        slot_date_obj = date_type.fromisoformat(slot_date) if isinstance(slot_date, str) else slot_date

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

    async def try_reserve_dispatch(
        self,
        slot_date: str,
        slot_time: str,
        chat_id: int,
        connection: asyncpg.Connection,
    ) -> bool:
        """Пытается забронировать право на отправку (оптимистическая бронь).

        Атомарно создает запись в реестре. Использует INSERT с ON CONFLICT
        для атомарного захвата. Возвращает True только если запись была создана
        (бронь получена), False если запись уже существовала (бронь не получена).

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_id: Идентификатор чата.
            connection: Соединение БД для использования в транзакции (обязательно).

        Returns:
            True если бронь получена (запись создана), False если уже забронировано.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        from datetime import date as date_type

        key = self._key(slot_date, slot_time, chat_id)
        slot_date_obj = date_type.fromisoformat(slot_date) if isinstance(slot_date, str) else slot_date

        try:
            # INSERT с ON CONFLICT DO NOTHING
            # Возвращает количество затронутых строк: 1 если создано, 0 если конфликт
            result: str = await connection.execute(
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
            # Проверяем количество затронутых строк
            # "INSERT 0 1" означает, что строка была создана (бронь получена)
            # "INSERT 0 0" означает конфликт (бронь не получена)
            return result == "INSERT 0 1"  # True если создано, False если конфликт
        except Exception as exc:
            self.logger.error(
                f"Ошибка при бронировании dispatch_registry (key={key}) в Postgres: {exc}",
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
