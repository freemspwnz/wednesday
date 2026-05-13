from __future__ import annotations

from types import TracebackType
from typing import Literal, overload

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.protocols import UoW

from .repos import (
    SQLAChatRepo,
    SQLAUserRepo,
)

REPO_REGISTRY: dict[str, type[SQLAUserRepo | SQLAChatRepo]] = {
    "users": SQLAUserRepo,
    "chats": SQLAChatRepo,
}


class SQLAUoW(UoW):
    """Unit of Work поверх SQLAlchemy AsyncSession.

    При выходе из контекста:
    - при отсутствии ошибок выполняется commit()
    - при наличии ошибок выполняется rollback()
    - сессия всегда закрывается
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self._repos: dict[str, SQLAUserRepo | SQLAChatRepo] = {}

    async def __aenter__(self) -> SQLAUoW:
        self.session = self._session_factory()
        await self.session.begin()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
        try:
            if exc_type is None:
                await self.session.commit()
            else:
                await self.session.rollback()
        except Exception:
            await self.session.rollback()
            raise
        finally:
            await self.session.close()
            self.session = None
            self._repos.clear()  # очистка репозиториев после транзакции

    def __getattr__(self, name: str) -> SQLAUserRepo | SQLAChatRepo:
        if name in REPO_REGISTRY:
            return self._get_repo(name)
        raise AttributeError(f"Repository {name} not found in UoW")

    @property
    def users(self) -> SQLAUserRepo:
        return self._get_repo("users")

    @property
    def chats(self) -> SQLAChatRepo:
        return self._get_repo("chats")

    @overload
    def _get_repo(self, name: Literal["users"]) -> SQLAUserRepo: ...

    @overload
    def _get_repo(self, name: Literal["chats"]) -> SQLAChatRepo: ...

    @overload
    def _get_repo(self, name: str) -> SQLAUserRepo | SQLAChatRepo: ...

    def _get_repo(self, name: str) -> SQLAUserRepo | SQLAChatRepo:
        if self.session is None:
            raise RuntimeError("Session not initialized. Use 'async with uow' context.")
        if self._repos.get(name) is None:
            self._repos[name] = REPO_REGISTRY[name](self.session)
        return self._repos[name]
