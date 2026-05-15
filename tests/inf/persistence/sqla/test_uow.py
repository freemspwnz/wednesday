from unittest.mock import AsyncMock, Mock

import pytest

from infra.persistence.sqlalchemy.repos import SQLAChatRepo, SQLAUserRepo
from infra.persistence.sqlalchemy.uow import SQLAUoW


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_uow_commits_on_success_and_caches_repositories() -> None:
    session = AsyncMock()
    session_factory = Mock(return_value=session)
    uow = SQLAUoW(session_factory=session_factory)

    async with uow as active:
        users_repo = active.users
        chats_repo = active.chats
        assert isinstance(users_repo, SQLAUserRepo)
        assert isinstance(chats_repo, SQLAChatRepo)
        assert active.users is users_repo

    session.begin.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.infra
@pytest.mark.asyncio
async def test_uow_rolls_back_on_error() -> None:
    session = AsyncMock()
    session_factory = Mock(return_value=session)
    uow = SQLAUoW(session_factory=session_factory)

    with pytest.raises(RuntimeError):
        async with uow:
            raise RuntimeError("boom")

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    session.close.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.infra
def test_uow_rejects_repo_access_outside_context() -> None:
    uow = SQLAUoW(session_factory=Mock())
    with pytest.raises(RuntimeError):
        _ = uow.users
