from types import TracebackType
from typing import Literal, Self, overload

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.protocols import UoW

from .repos import (
    SQLAChatRepo,
    SQLAImageRepo,
    SQLAUsageRepo,
    SQLAUserRepo,
    SQLAViewRepo,
    SQLAViolationRepo,
    SQLAVoteRepo,
)

RepoInstance = (
    SQLAChatRepo | SQLAImageRepo | SQLAViewRepo | SQLAVoteRepo | SQLAUsageRepo | SQLAUserRepo | SQLAViolationRepo
)

REPO_REGISTRY: dict[str, type[RepoInstance]] = {
    "users": SQLAUserRepo,
    "chats": SQLAChatRepo,
    "usage": SQLAUsageRepo,
    "violations": SQLAViolationRepo,
    "images": SQLAImageRepo,
    "views": SQLAViewRepo,
    "votes": SQLAVoteRepo,
}


class SQLAUoW(UoW):
    """Unit of Work over a SQLAlchemy ``AsyncSession``.

    On context exit:
    - commit when no error occurred
    - rollback on error
    - always close the session
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self._repos: dict[str, RepoInstance] = {}

    async def __aenter__(self) -> Self:
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
            self._repos.clear()  # clean repos after transaction

    def __getattr__(self, name: str) -> RepoInstance:
        if name in REPO_REGISTRY:
            return self._get_repo(name)
        raise AttributeError(f"Repository {name} not found in UoW")

    @property
    def users(self) -> SQLAUserRepo:
        return self._get_repo("users")

    @property
    def chats(self) -> SQLAChatRepo:
        return self._get_repo("chats")

    @property
    def usage(self) -> SQLAUsageRepo:
        return self._get_repo("usage")

    @property
    def violations(self) -> SQLAViolationRepo:
        return self._get_repo("violations")

    @property
    def images(self) -> SQLAImageRepo:
        return self._get_repo("images")

    @property
    def views(self) -> SQLAViewRepo:
        return self._get_repo("views")

    @property
    def votes(self) -> SQLAVoteRepo:
        return self._get_repo("votes")

    @overload
    def _get_repo(self, name: Literal["users"]) -> SQLAUserRepo: ...

    @overload
    def _get_repo(self, name: Literal["chats"]) -> SQLAChatRepo: ...

    @overload
    def _get_repo(self, name: Literal["usage"]) -> SQLAUsageRepo: ...

    @overload
    def _get_repo(self, name: Literal["violations"]) -> SQLAViolationRepo: ...

    @overload
    def _get_repo(self, name: Literal["images"]) -> SQLAImageRepo: ...

    @overload
    def _get_repo(self, name: Literal["views"]) -> SQLAViewRepo: ...

    @overload
    def _get_repo(self, name: Literal["votes"]) -> SQLAVoteRepo: ...

    @overload
    def _get_repo(self, name: str) -> RepoInstance: ...

    def _get_repo(self, name: str) -> RepoInstance:
        if self.session is None:
            raise RuntimeError("Session not initialized. Use 'async with uow' context.")
        if self._repos.get(name) is None:
            self._repos[name] = REPO_REGISTRY[name](self.session)
        return self._repos[name]
