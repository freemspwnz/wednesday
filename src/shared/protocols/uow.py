"""Протоколы Unit of Work для управления транзакциями."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    import asyncpg
else:
    import asyncpg

# TypeVar для типизации connection в Unit of Work
# Позволяет использовать разные типы connection (asyncpg.Connection, моки для тестов и т.д.)
ConnectionType = TypeVar("ConnectionType", bound=asyncpg.Connection)


@runtime_checkable
class IDatabaseUnitOfWork(Protocol[ConnectionType]):
    """Протокол для Unit of Work управления транзакциями БД.

    Использует TypeVar для типизации connection, что позволяет использовать
    разные типы connection (asyncpg.Connection, моки для тестов и т.д.).

    Type Parameters:
        ConnectionType: Тип соединения БД (по умолчанию asyncpg.Connection).
    """

    async def __aenter__(self) -> IDatabaseUnitOfWork[ConnectionType]:
        """Вход в контекстный менеджер. Начинает транзакцию."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Выход из контекстного менеджера. Коммитит или откатывает транзакцию."""
        ...

    @property
    def connection(self) -> ConnectionType:
        """Возвращает соединение БД для использования в репозиториях.

        Returns:
            Соединение БД, используемое в текущей транзакции.
            Тип определяется параметром ConnectionType протокола.

        Raises:
            RuntimeError: Если транзакция не начата.
        """
        ...


@runtime_checkable
class IUnitOfWorkFactory(Protocol[ConnectionType]):
    """Протокол для фабрики создания экземпляров Unit of Work.

    Использует TypeVar для типизации connection, что позволяет явно указать
    тип connection, возвращаемого Unit of Work.

    Type Parameters:
        ConnectionType: Тип соединения БД (по умолчанию asyncpg.Connection).
    """

    def __call__(self) -> IDatabaseUnitOfWork[ConnectionType]:
        """Создает новый экземпляр Unit of Work.

        Returns:
            Новый экземпляр IDatabaseUnitOfWork для использования в транзакции.
            Connection в возвращаемом Unit of Work будет иметь тип ConnectionType.
        """
        ...


@runtime_checkable
class IImageStorageUnitOfWork(Protocol):
    """Протокол для Unit of Work управления сохранением изображений."""

    async def save_image(
        self,
        image_data: bytes,
        caption: str,
        cache_key: str,
        storage_prefix: str = "frog",
    ) -> bool:
        """Сохраняет изображение в кэш и хранилище.

        Args:
            image_data: Байты изображения.
            caption: Подпись к изображению.
            cache_key: Ключ для кэша.
            storage_prefix: Префикс для файлового хранилища.

        Returns:
            True если сохранение успешно (хотя бы в одно хранилище), False иначе.
        """
        ...

    async def rollback(self) -> None:
        """Откатывает операции Unit of Work.

        Выполняет компенсационные действия для отката операций.
        """
        ...
