"""Tests for ThrottlingMiddleware."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.types import Update

from app.exceptions import LimitStorageError, TooManyRequests
from domain.chat import ChatType
from presentation.aiogram.messages import throttling as throttling_msg
from presentation.aiogram.middlewares.update.throttling import ThrottlingMiddleware

from ..factories import make_callback_query, mk_chat_context


@pytest.mark.unit
@pytest.mark.asyncio
async def test_passes_through_when_no_chat_in_data(mock_limiter: MagicMock, mock_logger: MagicMock) -> None:
    middleware = ThrottlingMiddleware(limiter=mock_limiter, logger=mock_logger)
    handler = AsyncMock(return_value="ok")
    event = MagicMock()
    data: dict[str, object] = {}

    result = await middleware(handler, event, data)

    assert result == "ok"
    handler.assert_awaited_once()
    mock_limiter.call.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calls_handler_when_limits_ok(mock_limiter: MagicMock, mock_logger: MagicMock) -> None:
    middleware = ThrottlingMiddleware(limiter=mock_limiter, logger=mock_logger)
    handler = AsyncMock(return_value="ok")
    chat = mk_chat_context(tg_id=42, chat_type=ChatType.PRIVATE)
    data: dict[str, object] = {"chat": chat}

    result = await middleware(handler, MagicMock(), data)

    assert result == "ok"
    assert mock_limiter.call.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fail_open_on_limit_storage_error(mock_limiter: MagicMock, mock_logger: MagicMock) -> None:
    mock_limiter.call.side_effect = LimitStorageError("down")
    middleware = ThrottlingMiddleware(limiter=mock_limiter, logger=mock_logger)
    handler = AsyncMock(return_value="ok")
    data: dict[str, object] = {"chat": mk_chat_context(tg_id=42, chat_type=ChatType.PRIVATE)}

    result = await middleware(handler, MagicMock(), data)

    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drops_update_and_warns_on_throttle(mock_limiter: MagicMock, mock_logger: MagicMock) -> None:
    mock_limiter.call.side_effect = [
        None,
        TooManyRequests(retry_after=1, reset_at=0.0, limit="user"),
        None,
    ]
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()
    middleware = ThrottlingMiddleware(limiter=mock_limiter, logger=mock_logger)
    handler = AsyncMock()
    data: dict[str, object] = {
        "chat": mk_chat_context(tg_id=42, chat_type=ChatType.PRIVATE),
        "bot": bot,
    }

    result = await middleware(handler, MagicMock(), data)

    assert result is None
    handler.assert_not_awaited()
    bot.send_message.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skips_warning_when_throttle_notify_limit_hit(
    mock_limiter: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_limiter.call.side_effect = [
        None,
        TooManyRequests(retry_after=1, reset_at=0.0, limit="user"),
        TooManyRequests(retry_after=1, reset_at=0.0, limit="throttling"),
    ]
    bot = AsyncMock(spec=Bot)
    middleware = ThrottlingMiddleware(limiter=mock_limiter, logger=mock_logger)
    handler = AsyncMock()
    data: dict[str, object] = {
        "chat": mk_chat_context(tg_id=-100, chat_type=ChatType.SUPERGROUP),
        "bot": bot,
    }

    await middleware(handler, MagicMock(), data)

    bot.send_message.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_throttled_callback_answers_personal_toast_not_chat(
    mock_limiter: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_limiter.call.side_effect = [
        None,
        TooManyRequests(retry_after=1, reset_at=0.0, limit="chat"),
        None,
    ]
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()
    bot.answer_callback_query = AsyncMock()
    middleware = ThrottlingMiddleware(limiter=mock_limiter, logger=mock_logger)
    handler = AsyncMock()
    callback = make_callback_query(data="imgvote:x:1", chat_id=-100)
    data: dict[str, object] = {
        "chat": mk_chat_context(tg_id=-100, chat_type=ChatType.SUPERGROUP),
        "bot": bot,
    }

    result = await middleware(handler, Update(update_id=1, callback_query=callback), data)

    assert result is None
    handler.assert_not_awaited()
    bot.send_message.assert_not_awaited()
    bot.answer_callback_query.assert_awaited_once()
    answered = bot.answer_callback_query.await_args
    assert answered.kwargs["callback_query_id"] == callback.id
    assert answered.kwargs["text"] in throttling_msg.PERSONAL
    assert "show_alert" not in answered.kwargs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_throttled_callback_answers_empty_when_notify_limit_hit(
    mock_limiter: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_limiter.call.side_effect = [
        None,
        TooManyRequests(retry_after=1, reset_at=0.0, limit="chat"),
        TooManyRequests(retry_after=1, reset_at=0.0, limit="throttling"),
    ]
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()
    bot.answer_callback_query = AsyncMock()
    middleware = ThrottlingMiddleware(limiter=mock_limiter, logger=mock_logger)
    handler = AsyncMock()
    callback = make_callback_query(data="imgvote:x:1", chat_id=-100)
    data: dict[str, object] = {
        "chat": mk_chat_context(tg_id=-100, chat_type=ChatType.SUPERGROUP),
        "bot": bot,
    }

    await middleware(handler, Update(update_id=1, callback_query=callback), data)

    handler.assert_not_awaited()
    bot.send_message.assert_not_awaited()
    bot.answer_callback_query.assert_awaited_once()
    answered = bot.answer_callback_query.await_args
    assert answered.kwargs["callback_query_id"] == callback.id
    assert answered.kwargs["text"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_group_chat_uses_chat_limit_key(mock_limiter: MagicMock, mock_logger: MagicMock) -> None:
    middleware = ThrottlingMiddleware(limiter=mock_limiter, logger=mock_logger)
    handler = AsyncMock()
    data: dict[str, object] = {"chat": mk_chat_context(tg_id=-1001, chat_type=ChatType.SUPERGROUP)}

    await middleware(handler, MagicMock(), data)

    assert mock_limiter.call.await_count == 2
    assert mock_limiter.call.await_args_list[1].args[1] == ThrottlingMiddleware._rl_throttle_key(-1001)


@pytest.mark.unit
def test_throttle_key_format() -> None:
    assert ThrottlingMiddleware._rl_throttle_key(99) == "throttle:99"
    assert ThrottlingMiddleware._rl_throttle_key(-100) == "throttle:-100"
