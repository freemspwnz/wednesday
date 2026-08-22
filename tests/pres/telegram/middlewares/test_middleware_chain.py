"""End-to-end: production update middleware chain (DI → Registration → Throttling → handler)."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ChatMemberStatus
from aiogram.types import (
    Chat,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberUpdated,
    Message,
    Update,
    User,
)

from app.exceptions import TooManyRequests
from presentation.aiogram.middlewares.update.di import DIMiddleware
from presentation.aiogram.middlewares.update.registration import RegistrationMiddleware
from presentation.aiogram.middlewares.update.throttling import ThrottlingMiddleware

from ..factories import ScopeCM, make_callback_query, make_message, mk_chat_context, mk_user_context

_MSG_DATE = datetime(2026, 1, 1, tzinfo=UTC)


def _register_production_update_middlewares(
    dp: Dispatcher,
    *,
    scope: MagicMock,
    limiter: MagicMock,
    logger: MagicMock,
) -> None:
    """Same registration order as ``setup_dp``: DI → Registration → Throttling → handler."""
    di_mw = DIMiddleware(scope=scope, logger=logger)
    dp.update.middleware(di_mw)
    dp.update.middleware(RegistrationMiddleware(logger=logger))
    dp.update.middleware(ThrottlingMiddleware(limiter=limiter, logger=logger))


def _bot_left_event() -> ChatMemberUpdated:
    bot = User(id=1, is_bot=True, first_name="Bot")
    old = ChatMemberMember(user=bot, status=ChatMemberStatus.MEMBER)
    new = ChatMemberLeft(user=bot, status=ChatMemberStatus.LEFT)
    return ChatMemberUpdated(
        chat=Chat(id=-100, type="supergroup"),
        from_user=User(id=99, is_bot=False, first_name="Admin"),
        date=_MSG_DATE,
        old_chat_member=old,
        new_chat_member=new,
    )


async def _feed(dp: Dispatcher, update: Update) -> dict[str, Any]:
    bot = AsyncMock(spec=Bot)
    captured: dict[str, Any] = {}
    router = Router(name="probe")

    @router.message()
    async def on_message(
        _: Message,
        scope: object,
        user: object,
        chat: object,
        logger: object,
    ) -> None:
        captured["scope"] = scope
        captured["user"] = user
        captured["chat"] = chat
        captured["logger"] = logger

    @router.callback_query()
    async def on_callback(
        _: object,
        scope: object,
        user: object,
        chat: object,
        logger: object,
    ) -> None:
        captured["scope"] = scope
        captured["user"] = user
        captured["chat"] = chat
        captured["logger"] = logger

    @router.my_chat_member()
    async def on_my_chat_member(
        __: ChatMemberUpdated,
        scope: object,
        user: object,
        chat: object,
    ) -> None:
        captured["scope"] = scope
        captured["user"] = user
        captured["chat"] = chat

    dp.include_router(router)
    await dp.feed_update(bot, update)
    return captured


@pytest.mark.unit
@pytest.mark.asyncio
async def test_message_chain_injects_scope_registers_and_throttles(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    mock_limiter: MagicMock,
) -> None:
    reg_user = mk_user_context()
    reg_chat = mk_chat_context(tg_id=1)
    mock_scope.user_lifecycle_uc.register.return_value = reg_user
    mock_scope.chat_management_uc.register.return_value = reg_chat
    mock_scope.logger = mock_logger

    dp = Dispatcher()
    _register_production_update_middlewares(
        dp,
        scope=MagicMock(return_value=ScopeCM(mock_scope)),
        limiter=mock_limiter,
        logger=mock_logger,
    )

    captured = await _feed(dp, Update(update_id=1, message=make_message()))

    assert captured["scope"] is mock_scope
    assert captured["logger"] is mock_logger
    assert captured["user"] == reg_user
    assert captured["chat"] == reg_chat
    mock_scope.user_lifecycle_uc.register.assert_awaited_once()
    mock_scope.chat_management_uc.register.assert_awaited_once()
    assert mock_limiter.call.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_callback_query_chain_registers_user_and_chat(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    mock_limiter: MagicMock,
) -> None:
    reg_user = mk_user_context()
    reg_chat = mk_chat_context(tg_id=1)
    mock_scope.user_lifecycle_uc.register.return_value = reg_user
    mock_scope.chat_management_uc.register.return_value = reg_chat
    mock_scope.logger = mock_logger

    dp = Dispatcher()
    _register_production_update_middlewares(
        dp,
        scope=MagicMock(return_value=ScopeCM(mock_scope)),
        limiter=mock_limiter,
        logger=mock_logger,
    )

    captured = await _feed(
        dp,
        Update(update_id=4, callback_query=make_callback_query(data="imgvote:x:1")),
    )

    assert captured["scope"] is mock_scope
    assert captured["user"] == reg_user
    assert captured["chat"] == reg_chat
    mock_scope.user_lifecycle_uc.register.assert_awaited_once()
    mock_scope.chat_management_uc.register.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bot_left_skips_registration_in_chain(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    mock_limiter: MagicMock,
) -> None:
    mock_scope.logger = mock_logger
    dp = Dispatcher()
    _register_production_update_middlewares(
        dp,
        scope=MagicMock(return_value=ScopeCM(mock_scope)),
        limiter=mock_limiter,
        logger=mock_logger,
    )

    captured = await _feed(dp, Update(update_id=2, my_chat_member=_bot_left_event()))

    assert captured["scope"] is mock_scope
    assert captured["user"] is None
    assert captured["chat"] is None
    mock_scope.user_lifecycle_uc.register.assert_not_awaited()
    mock_scope.chat_management_uc.register.assert_not_awaited()
    mock_limiter.call.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_throttling_drops_update_before_handler(
    mock_scope: MagicMock,
    mock_logger: MagicMock,
    mock_limiter: MagicMock,
) -> None:
    reg_chat = mk_chat_context(tg_id=1)
    mock_scope.user_lifecycle_uc.register.return_value = mk_user_context()
    mock_scope.chat_management_uc.register.return_value = reg_chat
    mock_scope.logger = mock_logger
    mock_limiter.call.side_effect = [
        None,
        TooManyRequests(retry_after=1, reset_at=0.0, limit="user"),
        None,
    ]

    dp = Dispatcher()
    _register_production_update_middlewares(
        dp,
        scope=MagicMock(return_value=ScopeCM(mock_scope)),
        limiter=mock_limiter,
        logger=mock_logger,
    )

    captured = await _feed(dp, Update(update_id=3, message=make_message()))

    assert captured == {}
