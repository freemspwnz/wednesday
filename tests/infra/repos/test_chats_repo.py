from typing import Any

import pytest

from infra.repos import ChatsRepo

pytestmark = [
    pytest.mark.integration,
    pytest.mark.db,
    pytest.mark.usefixtures("_setup_test_postgres"),
]


@pytest.mark.asyncio
async def test_chats_store_add_chat(postgres_transaction: Any, async_postgres_pool: Any) -> None:
    store = ChatsRepo(pool=async_postgres_pool)

    await store.add_chat(12345, "Test Chat")

    chat_ids = await store.list_chat_ids()
    assert 12345 in chat_ids


@pytest.mark.asyncio
async def test_chats_store_remove_chat(postgres_transaction: Any, async_postgres_pool: Any) -> None:
    store = ChatsRepo(pool=async_postgres_pool)

    await store.add_chat(12345, "Test Chat")
    await store.remove_chat(12345)

    chat_ids = await store.list_chat_ids()
    assert 12345 not in chat_ids


@pytest.mark.asyncio
async def test_chats_store_list_chat_ids(postgres_transaction: Any, async_postgres_pool: Any) -> None:
    store = ChatsRepo(pool=async_postgres_pool)

    await store.add_chat(11111, "Chat 1")
    await store.add_chat(22222, "Chat 2")
    await store.add_chat(33333, "Chat 3")

    chat_ids = await store.list_chat_ids()
    assert len(chat_ids) == 3
    assert 11111 in chat_ids
    assert 22222 in chat_ids
    assert 33333 in chat_ids


@pytest.mark.asyncio
async def test_chats_store_list_chat_ids_empty(cleanup_tables: Any, async_postgres_pool: Any) -> None:
    store = ChatsRepo(pool=async_postgres_pool)

    chat_ids = await store.list_chat_ids()
    assert chat_ids == []
