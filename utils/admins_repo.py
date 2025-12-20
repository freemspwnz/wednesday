"""
Хранилище администраторов на базе PostgreSQL.

Ранее состояние хранилось в JSON-файле `data/admins.json`, теперь все данные
перенесены в таблицу `admins` (см. `utils.postgres_schema`).
"""

from __future__ import annotations

import asyncpg

from utils.config import config
from utils.logger import get_logger, log_all_methods


@log_all_methods()
class AdminsRepo:
    """
    Репозиторий для управления списком администраторов.

    Главный админ по-прежнему задаётся через переменную окружения ADMIN_CHAT_ID
    и всегда имеет права независимо от содержимого таблицы.
    """

    def __init__(self, pool: asyncpg.Pool, storage_path: str | None = None) -> None:
        """Инициализирует репозиторий администраторов.

        Args:
            pool: Пул подключений PostgreSQL.
            storage_path: Параметр оставлен для обратной совместимости и игнорируется.
        """
        # storage_path оставлен для обратной совместимости и игнорируется.
        self._pool = pool
        self.logger = get_logger(__name__)

    async def is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором.

        Проверяет наличие пользователя в таблице admins или сравнивает
        с главным администратором из переменной окружения ADMIN_CHAT_ID.

        Args:
            user_id: Идентификатор пользователя для проверки.

        Returns:
            True если пользователь является администратором, False иначе.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        # Главный админ из .env всегда имеет права
        main_admin = config.admin_chat_id
        if main_admin and int(main_admin) == user_id:
            return True

        async with self._pool.acquire() as conn:
            try:
                row = await conn.fetchrow("SELECT 1 FROM admins WHERE user_id = $1;", int(user_id))
            except Exception as exc:
                self.logger.error(f"Ошибка при проверке прав админа {user_id} в Postgres: {exc}")
                raise
        return row is not None

    async def add_admin(self, user_id: int) -> bool:
        """Добавляет администратора в таблицу admins.

        Args:
            user_id: Идентификатор пользователя для добавления в список администраторов.

        Returns:
            True если администратор был добавлен, False если он уже существовал.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        async with self._pool.acquire() as conn:
            try:
                result = await conn.execute(
                    """
                    INSERT INTO admins (user_id)
                    VALUES ($1)
                    ON CONFLICT (user_id) DO NOTHING;
                    """,
                    int(user_id),
                )
                # asyncpg возвращает строку вида "INSERT 0 1" / "INSERT 0 0"
                inserted = str(result).endswith("1")
                if inserted:
                    self.logger.info(f"Добавлен администратор {user_id} в Postgres")
                else:
                    self.logger.info(f"Администратор {user_id} уже существует в Postgres")
                return inserted
            except Exception as exc:
                self.logger.error(f"Ошибка при добавлении админа {user_id} в Postgres: {exc}")
                raise

    async def remove_admin(self, user_id: int) -> bool:
        """Удаляет администратора из таблицы admins.

        Args:
            user_id: Идентификатор пользователя для удаления из списка администраторов.

        Returns:
            True если администратор был удалён, False если он не был администратором.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        async with self._pool.acquire() as conn:
            try:
                result = await conn.execute("DELETE FROM admins WHERE user_id = $1;", int(user_id))
                deleted = str(result).endswith("1")
                if deleted:
                    self.logger.info(f"Администратор {user_id} удалён из Postgres")
                else:
                    self.logger.info(f"Администратор {user_id} не найден в Postgres")
                return deleted
            except Exception as exc:
                self.logger.error(f"Ошибка при удалении админа {user_id} из Postgres: {exc}")
                raise

    async def list_admins(self) -> list[int]:
        """Возвращает список всех администраторов из таблицы admins.

        Главный администратор из переменной окружения ADMIN_CHAT_ID не включается
        в результат.

        Returns:
            Список идентификаторов администраторов, отсортированный по user_id.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        async with self._pool.acquire() as conn:
            try:
                rows = await conn.fetch("SELECT user_id FROM admins ORDER BY user_id;")
                return [int(row["user_id"]) for row in rows]
            except Exception as exc:
                self.logger.error(f"Ошибка при получении списка админов из Postgres: {exc}")
                raise

    async def list_all_admins(self) -> list[int]:
        """Возвращает список всех администраторов, включая главного из .env.

        Включает администраторов из таблицы admins и главного администратора
        из переменной окружения ADMIN_CHAT_ID (если задан).

        Returns:
            Список идентификаторов всех администраторов. Главный администратор
            (если задан) всегда находится в начале списка.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        admin_ids = await self.list_admins()
        main_admin = config.admin_chat_id
        if main_admin:
            main_id = int(main_admin)
            if main_id not in admin_ids:
                admin_ids.insert(0, main_id)
        return admin_ids
