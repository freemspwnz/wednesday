"""Tests for ChatManagementUseCase."""

from unittest.mock import AsyncMock

import pytest

from app.dto import ChatContext
from domain.chat import (
    AccessDeniedError,
    ActiveState,
    ChatProfile,
    ChatType,
)
from domain.chat.exceptions import InvalidStateTransitionError

from ...factories import mk_chat_context
from .helpers import dt, make_management_uc, member_actor, mk_chat, owner_actor


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_loads_and_caches() -> None:
    repo = AsyncMock()
    uc, _, cache = make_management_uc(repo=repo)
    profile = ChatProfile(type=ChatType.GROUP, telegram_id=-100, title="T")
    cache.chats.get_by_id.return_value = None
    domain_chat = mk_chat(chat_id=7, telegram_id=-100, now=dt(10))

    repo.get_by_id.return_value = domain_chat
    got = await uc.register(profile=profile)

    assert isinstance(got, ChatContext)
    assert got.tg_id == -100
    cache.chats.set.assert_awaited_once_with(domain_chat)
    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_returns_cached_value_without_uow() -> None:
    repo = AsyncMock()
    uc, uow, cache = make_management_uc(repo=repo)
    profile = ChatProfile(type=ChatType.GROUP, telegram_id=-100, title="T")
    cached = mk_chat_context(tg_id=-100, chat_type=ChatType.GROUP)
    cache.chats.get_by_id.return_value = cached

    got = await uc.register(profile=profile)

    assert got is cached
    assert uow.enter_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_find_by_tg_id_loads_from_db_without_create() -> None:
    repo = AsyncMock()
    uc, _, cache = make_management_uc(repo=repo)
    cache.chats.get_by_id.return_value = None
    domain_chat = mk_chat(chat_id=8, telegram_id=-200, now=dt(10))

    repo.get_by_id.return_value = domain_chat
    got = await uc.find_by_tg_id(tg_id=-200)

    assert isinstance(got, ChatContext)
    assert got.tg_id == -200
    repo.get_by_id.assert_awaited_once()
    cache.chats.set.assert_awaited_once_with(domain_chat)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_change_profile_happy_path_persists_and_closes_uow() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, uow, cache = make_management_uc(repo=repo)
    new_profile = ChatProfile(type=ChatType.GROUP, telegram_id=-1001, title="Ops")

    got = await uc.change_profile(
        chat_id=chat.id,
        actor=owner_actor(chat),
        new_profile=new_profile,
        at=dt(11),
    )

    assert got.profile == new_profile
    repo.get_by_id.assert_awaited_once_with(chat.id)
    repo.save.assert_awaited_once_with(chat)
    assert uow.enter_count == uow.exit_count == 1
    cache.chats.set.assert_awaited_once_with(got)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_management_access_denied_propagates_and_skips_save() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _, _cache = make_management_uc(repo=repo)
    new_profile = ChatProfile(type=ChatType.GROUP, telegram_id=-1001, title="X")

    with pytest.raises(AccessDeniedError):
        await uc.change_profile(
            chat_id=chat.id,
            actor=member_actor(chat),
            new_profile=new_profile,
            at=dt(11),
        )

    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_deactivate_and_activate_happy_path() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _, cache = make_management_uc(repo=repo)

    await uc.deactivate(chat_id=chat.id, actor=owner_actor(chat), at=dt(11))
    await uc.activate(chat_id=chat.id, actor=owner_actor(chat), at=dt(12))

    assert isinstance(chat.state, ActiveState)
    assert repo.save.await_count == 2
    assert cache.chats.set.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_activate_when_already_active_propagates() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _, _cache = make_management_uc(repo=repo)

    with pytest.raises(InvalidStateTransitionError):
        await uc.activate(chat_id=chat.id, actor=owner_actor(chat), at=dt(11))

    repo.save.assert_not_awaited()
