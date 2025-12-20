"""
Трекер использования генераций изображений по месяцам на базе PostgreSQL.

Ранее статистика хранилась в JSON-файле `data/usage_stats.json`. Теперь:
- помесячные значения лежат в таблице `usage_stats`;
- настройки квот — в таблице `usage_settings` (единая строка id=1).
"""

from __future__ import annotations

from datetime import datetime

import asyncpg

from utils.logger import get_logger, log_all_methods
from utils.postgres_client import get_postgres_pool


@log_all_methods()
class UsageTracker:
    """
    Учет количества генераций изображений по месяцам.

    Вся статистика хранится в Postgres и доступна через асинхронные методы.
    """

    def __init__(
        self,
        storage_path: str | None = None,
        monthly_quota: int = 100,
        frog_threshold: int = 70,
        pool: asyncpg.Pool | None = None,
    ) -> None:
        """Инициализирует трекер использования генераций.

        Args:
            storage_path: Параметр оставлен для обратной совместимости и игнорируется.
            monthly_quota: Месячная квота генераций (по умолчанию 100).
            frog_threshold: Порог для ручных генераций /frog (по умолчанию 70).
            pool: Пул подключений PostgreSQL. Если None, используется глобальный пул
                  (для обратной совместимости).
        """
        self._pool = pool or get_postgres_pool()
        self.logger = get_logger(__name__)
        self.monthly_quota = int(monthly_quota)
        self.frog_threshold = int(frog_threshold)

    @staticmethod
    def _month_key(dt: datetime) -> str:
        """Формирует ключ месяца в формате YYYY-MM.

        Args:
            dt: Дата для формирования ключа.

        Returns:
            Строка в формате YYYY-MM (например, "2024-01").
        """
        return dt.strftime("%Y-%m")

    async def _ensure_settings_row(self) -> None:
        """Гарантирует наличие строки настроек (id=1) с актуальными значениями квот.

        Создаёт или обновляет строку с id=1 в таблице usage_settings
        с текущими значениями monthly_quota и frog_threshold.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO usage_settings (id, monthly_quota, frog_threshold)
                VALUES (1, $1, $2)
                ON CONFLICT (id) DO UPDATE
                SET monthly_quota = EXCLUDED.monthly_quota,
                    frog_threshold = EXCLUDED.frog_threshold;
                """,
                int(self.monthly_quota),
                int(self.frog_threshold),
            )

    async def increment(self, count: int = 1, when: datetime | None = None) -> int:
        """Увеличивает счётчик генераций за месяц и возвращает новое значение.

        Args:
            count: Количество генераций для добавления (по умолчанию 1).
            when: Дата для учёта генераций. Если не указана, используется текущая дата UTC.

        Returns:
            Новое значение счётчика генераций за месяц.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        await self._ensure_settings_row()
        dt = when or datetime.utcnow()
        key = self._month_key(dt)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT count FROM usage_stats WHERE month = $1;",
                key,
            )
            current = int(row["count"]) if row is not None else 0
            new_value = current + int(count)
            await conn.execute(
                """
                INSERT INTO usage_stats (month, count)
                VALUES ($1, $2)
                ON CONFLICT (month) DO UPDATE
                SET count = EXCLUDED.count;
                """,
                key,
                new_value,
            )
        return new_value

    async def get_month_total(self, when: datetime | None = None) -> int:
        """Возвращает общее количество генераций за месяц.

        Args:
            when: Дата для получения статистики. Если не указана, используется текущая дата UTC.

        Returns:
            Количество генераций за указанный месяц. Если записей нет, возвращает 0.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        await self._ensure_settings_row()
        dt = when or datetime.utcnow()
        key = self._month_key(dt)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT count FROM usage_stats WHERE month = $1;",
                key,
            )
        return int(row["count"]) if row is not None else 0

    async def _load_settings(self) -> None:
        """Обновляет значения квот из таблицы usage_settings.

        Загружает актуальные значения monthly_quota и frog_threshold
        из базы данных и обновляет соответствующие атрибуты объекта.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT monthly_quota, frog_threshold FROM usage_settings WHERE id = 1;",
            )
        if row is not None:
            self.monthly_quota = int(row["monthly_quota"])
            self.frog_threshold = int(row["frog_threshold"])

    async def can_use_frog(self, when: datetime | None = None) -> bool:
        """Проверяет, не превышен ли порог ручных /frog для месяца.

        Args:
            when: Дата для проверки. Если не указана, используется текущая дата UTC.

        Returns:
            True если можно использовать команду /frog (не превышен порог),
            False иначе.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        await self._ensure_settings_row()
        await self._load_settings()
        total = await self.get_month_total(when)
        return total < self.frog_threshold

    async def get_limits_info(self, when: datetime | None = None) -> tuple[int, int, int]:
        """Возвращает информацию о лимитах использования для месяца.

        Args:
            when: Дата для получения информации. Если не указана, используется текущая дата UTC.

        Returns:
            Кортеж (total, frog_threshold, monthly_quota), где:
            - total: текущее количество использованных генераций
            - frog_threshold: порог для ручных генераций /frog
            - monthly_quota: месячная квота генераций

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        await self._ensure_settings_row()
        await self._load_settings()
        total = await self.get_month_total(when)
        return total, self.frog_threshold, self.monthly_quota

    async def set_month_total(self, total: int, when: datetime | None = None) -> int:
        """Устанавливает текущее значение использования за месяц в абсолютном виде.

        Args:
            total: Абсолютное значение счётчика генераций для установки.
            when: Дата для установки значения. Если не указана, используется текущая дата UTC.

        Returns:
            Установленное значение счётчика.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        await self._ensure_settings_row()
        dt = when or datetime.utcnow()
        key = self._month_key(dt)
        value = int(total)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO usage_stats (month, count)
                VALUES ($1, $2)
                ON CONFLICT (month) DO UPDATE
                SET count = EXCLUDED.count;
                """,
                key,
                value,
            )
        return value

    async def set_frog_threshold(self, threshold: int) -> int:
        """Устанавливает порог ручных генераций (/frog).

        Порог автоматически ограничивается диапазоном [0, monthly_quota].

        Args:
            threshold: Новое значение порога для ручных генераций.

        Returns:
            Установленное значение порога (после ограничения диапазоном).

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        await self._ensure_settings_row()
        threshold = max(int(threshold), 0)
        threshold = min(threshold, self.monthly_quota)
        self.frog_threshold = threshold

        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE usage_settings SET frog_threshold = $1 WHERE id = 1;",
                int(self.frog_threshold),
            )
        return self.frog_threshold
