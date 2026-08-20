"""Tests for ChatManagementUseCase."""

from unittest.mock import AsyncMock

import pytest

from app.dto import ChatContext
from domain.chat import (
    AccessDeniedError,
    ActiveState,
    ChatId,
    ChatType,
    InactiveState,
    System,
)
from domain.chat.exceptions import InvalidStateTransitionError

from ...factories import mk_chat_context, mk_logger
from .helpers import (
    dt,
    make_management_uc,
    member_kwargs,
    mk_chat,
    mk_chat_for_tg,
    owner_kwargs,
    plain_dt,
    register_kwargs,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_loads_and_caches() -> None:
    repo = AsyncMock()
    uc, _, cache = make_management_uc(repo=repo)
    cache.chats.get_by_id.return_value = None
    domain_chat = mk_chat_for_tg(tg_id=-100, now=dt(10))

    repo.get_by_id.return_value = domain_chat
    got = await uc.register(**register_kwargs(tg_id=-100, at=plain_dt(10)))

    assert isinstance(got, ChatContext)
    assert got.tg_id == -100
    cache.chats.set.assert_awaited_once()
    assert isinstance(cache.chats.set.await_args.args[0], ChatContext)
    repo.save.assert_not_awaited()
    repo.get_by_id.assert_awaited_once_with(ChatId.from_int(-100))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_returns_cached_value_without_uow() -> None:
    repo = AsyncMock()
    uc, uow, cache = make_management_uc(repo=repo)
    cached = mk_chat_context(tg_id=-100, chat_type=ChatType.GROUP)
    cache.chats.get_by_id.return_value = cached

    got = await uc.register(**register_kwargs(tg_id=-100))

    assert got is cached
    assert uow.enter_count == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_logs_info_on_first_create() -> None:
    log = mk_logger()
    repo = AsyncMock()
    uc, _, cache = make_management_uc(repo=repo, logger=log)
    cache.chats.get_by_id.return_value = None
    repo.get_by_id.return_value = None

    got = await uc.register(**register_kwargs(tg_id=-100))

    assert got.tg_id == -100
    assert got.id == str(ChatId.from_int(-100))
    repo.save.assert_awaited_once()
    log.info.assert_called_once_with("Chat registered", tg_id=-100)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_register_skips_info_for_existing_chat() -> None:
    log = mk_logger()
    repo = AsyncMock()
    uc, _, cache = make_management_uc(repo=repo, logger=log)
    cache.chats.get_by_id.return_value = None
    domain_chat = mk_chat_for_tg(tg_id=-100, now=dt(10))
    repo.get_by_id.return_value = domain_chat

    await uc.register(**register_kwargs(tg_id=-100, at=plain_dt(10)))

    log.info.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_find_by_tg_id_loads_from_db_without_create() -> None:
    repo = AsyncMock()
    uc, _, cache = make_management_uc(repo=repo)
    cache.chats.get_by_id.return_value = None
    domain_chat = mk_chat_for_tg(tg_id=-200, now=dt(10))

    repo.get_by_id.return_value = domain_chat
    got = await uc.find_by_tg_id(tg_id=-200)

    assert isinstance(got, ChatContext)
    assert got.tg_id == -200
    repo.get_by_id.assert_awaited_once_with(ChatId.from_int(-200))
    cache.chats.set.assert_awaited_once()
    assert isinstance(cache.chats.set.await_args.args[0], ChatContext)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_deactivate_and_activate_happy_path() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _, cache = make_management_uc(repo=repo)

    deactivated = await uc.deactivate(**owner_kwargs(chat), at=plain_dt(11))
    activated = await uc.activate(**owner_kwargs(chat), at=plain_dt(12))

    assert isinstance(chat.state, ActiveState)
    assert deactivated.is_active is False
    assert activated.is_active is True
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
        await uc.activate(**owner_kwargs(chat), at=plain_dt(11))

    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_deactivate_access_denied_propagates_and_skips_save() -> None:
    repo = AsyncMock()
    chat = mk_chat(now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _, cache = make_management_uc(repo=repo)

    with pytest.raises(AccessDeniedError):
        await uc.deactivate(**member_kwargs(chat), at=plain_dt(11))

    repo.save.assert_not_awaited()
    cache.chats.set.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_on_bot_kicked_returns_none_when_chat_missing() -> None:
    repo = AsyncMock()
    uc, _, cache = make_management_uc(repo=repo)
    cache.chats.get_by_id.return_value = None
    repo.get_by_id.return_value = None

    got = await uc.on_bot_kicked(tg_id=-404, at=plain_dt(11))

    assert got is None
    repo.save.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_on_bot_kicked_deactivates_active_chat() -> None:
    repo = AsyncMock()
    chat = mk_chat_for_tg(tg_id=-300, now=dt(10))
    repo.get_by_id.return_value = chat
    uc, _, cache = make_management_uc(repo=repo)
    cache.chats.get_by_id.return_value = None

    got = await uc.on_bot_kicked(tg_id=-300, at=plain_dt(11))

    assert isinstance(got, ChatContext)
    assert got.is_active is False
    assert isinstance(chat.state, InactiveState)
    repo.save.assert_awaited_once_with(chat)
    cache.chats.set.assert_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_uc_on_bot_kicked_is_idempotent_when_already_inactive() -> None:
    repo = AsyncMock()
    chat = mk_chat_for_tg(tg_id=-301, now=dt(10))
    chat.deactivate(actor=System(), at=dt(10))
    chat.pull_events()
    cached = ChatContext.from_domain(chat)
    uc, _, cache = make_management_uc(repo=repo)
    cache.chats.get_by_id.return_value = cached
    repo.get_by_id.return_value = chat

    got = await uc.on_bot_kicked(tg_id=-301, at=plain_dt(11))

    assert got is cached
    assert got.is_active is False
    repo.save.assert_not_awaited()
