"""Tests for ThrottlingMiddleware."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot

from app.exceptions import LimitStorageError, TooManyRequests
from domain.chat import ChatType
from presentation.aiogram.middlewares.update.throttling import ThrottlingMiddleware

from ..factories import mk_chat_context


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
