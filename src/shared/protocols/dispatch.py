"""Протоколы для работы с рассылкой и очисткой данных."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import asyncpg
else:
    import asyncpg


@runtime_checkable
class IDispatchRegistry(Protocol):
    """Протокол для реестра отправленных сообщений по тайм-слотам и чатам."""

    async def is_dispatched(self, slot_date: str, slot_time: str, chat_id: int) -> bool:
        """Проверяет, было ли уже отправлено сообщение в указанный слот и чат.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_id: Идентификатор чата для проверки.

        Returns:
            True если сообщение уже было отправлено, False иначе.
        """
        ...

    async def mark_dispatched(
        self,
        slot_date: str,
        slot_time: str,
        chat_id: int,
        connection: asyncpg.Connection,
    ) -> None:
        """Помечает сочетание (дата, время, чат) как уже отправленное.

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_id: Идентификатор чата для пометки.
            connection: Соединение БД для использования в транзакции (обязательно).
        """
        ...

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
        ...

    async def try_reserve_dispatch(
        self,
        slot_date: str,
        slot_time: str,
        chat_id: int,
        connection: asyncpg.Connection,
    ) -> bool:
        """Пытается забронировать право на отправку (оптимистическая бронь).

        Атомарно создает запись в реестре. Если запись уже существует,
        возвращает False (бронь не получена). Если запись создана успешно,
        возвращает True (бронь получена).

        Args:
            slot_date: Дата слота в формате YYYY-MM-DD.
            slot_time: Время слота в формате HH:MM.
            chat_id: Идентификатор чата.
            connection: Соединение БД для использования в транзакции (обязательно).

        Returns:
            True если бронь получена (запись создана), False если уже забронировано
            (запись уже существует).

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        ...

    async def cleanup_old(self) -> None:
        """Удаляет старые записи реестра старше retention_days.

        Удаляет все записи, у которых created_at меньше текущей даты
        минус retention_days дней.

        Raises:
            Exception: При ошибке доступа к базе данных PostgreSQL.
        """
        ...


@runtime_checkable
class IDataCleanupService(Protocol):
    """Протокол для сервиса очистки устаревших данных."""

    async def cleanup_all(self) -> None:
        """Выполняет очистку всех типов устаревших данных.

        Выполняет:
        - Очистку старых записей dispatch_registry
        - Другие операции очистки (если добавлены в будущем)

        Raises:
            Exception: При ошибке выполнения очистки.
        """
        ...
