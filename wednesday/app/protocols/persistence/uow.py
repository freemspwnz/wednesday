"""Протоколы Unit of Work для управления транзакциями."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, runtime_checkable

from domain.chat import ChatRepo
from domain.user import UserRepo


@runtime_checkable
class UoW(Protocol):
    """Протокол для Unit of Work управления транзакциями БД."""

    async def __aenter__(self) -> UoW:
        """Вход в контекстный менеджер. Начинает транзакцию."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Выход из контекстного менеджера. Коммитит или откатывает транзакцию."""
        ...

    @property
    def users(self) -> UserRepo: ...

    @property
    def chats(self) -> ChatRepo: ...


@runtime_checkable
class UoWFactory(Protocol):
    """Протокол для фабрики создания экземпляров Unit of Work."""

    def __call__(self) -> UoW:
        """Создает новый экземпляр Unit of Work.

        Returns:
            Новый экземпляр UoW для использования в транзакции.
        """
        ...
