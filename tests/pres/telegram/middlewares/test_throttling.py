"""Tests for ThrottlingMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot

from app.dto import ChatContext
from app.exceptions import LimitStorageError, TooManyRequests
from domain.chat import ChatType
from presentation.aiogram.middlewares.update.throttling import ThrottlingMiddleware


@pytest.mark.unit
@pytest.mark.asyncio
async def test_passes_through_when_no_chat_in_data(mock_rate_limiter: MagicMock, mock_logger: MagicMock) -> None:
    middleware = ThrottlingMiddleware(rate_limiter=mock_rate_limiter, logger=mock_logger)
    handler = AsyncMock(return_value="ok")
    event = MagicMock()
    data: dict[str, object] = {}

    result = await middleware(handler, event, data)

    assert result == "ok"
    handler.assert_awaited_once()
    mock_rate_limiter.call.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_calls_handler_when_limits_ok(mock_rate_limiter: MagicMock, mock_logger: MagicMock) -> None:
    middleware = ThrottlingMiddleware(rate_limiter=mock_rate_limiter, logger=mock_logger)
    handler = AsyncMock(return_value="ok")
    chat = ChatContext(tg_id=42, type=ChatType.PRIVATE)
    data: dict[str, object] = {"chat": chat}

    result = await middleware(handler, MagicMock(), data)

    assert result == "ok"
    assert mock_rate_limiter.call.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fail_open_on_limit_storage_error(mock_rate_limiter: MagicMock, mock_logger: MagicMock) -> None:
    mock_rate_limiter.call.side_effect = LimitStorageError("down")
    middleware = ThrottlingMiddleware(rate_limiter=mock_rate_limiter, logger=mock_logger)
    handler = AsyncMock(return_value="ok")
    data: dict[str, object] = {"chat": ChatContext(tg_id=42, type=ChatType.PRIVATE)}

    result = await middleware(handler, MagicMock(), data)

    assert result == "ok"
    handler.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_drops_update_and_warns_on_throttle(mock_rate_limiter: MagicMock, mock_logger: MagicMock) -> None:
    mock_rate_limiter.call.side_effect = [
        None,
        TooManyRequests(retry_after=1, reset_at=0.0, limit="user"),
        None,
    ]
    bot = AsyncMock(spec=Bot)
    bot.send_message = AsyncMock()
    middleware = ThrottlingMiddleware(rate_limiter=mock_rate_limiter, logger=mock_logger)
    handler = AsyncMock()
    data: dict[str, object] = {
        "chat": ChatContext(tg_id=42, type=ChatType.PRIVATE),
        "bot": bot,
    }

    result = await middleware(handler, MagicMock(), data)

    assert result is None
    handler.assert_not_awaited()
    bot.send_message.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_skips_warning_when_throttle_notify_limit_hit(
    mock_rate_limiter: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_rate_limiter.call.side_effect = [
        None,
        TooManyRequests(retry_after=1, reset_at=0.0, limit="user"),
        TooManyRequests(retry_after=1, reset_at=0.0, limit="throttling"),
    ]
    bot = AsyncMock(spec=Bot)
    middleware = ThrottlingMiddleware(rate_limiter=mock_rate_limiter, logger=mock_logger)
    handler = AsyncMock()
    data: dict[str, object] = {
        "chat": ChatContext(tg_id=-100, type=ChatType.SUPERGROUP),
        "bot": bot,
    }

    await middleware(handler, MagicMock(), data)

    bot.send_message.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_group_chat_uses_chat_limit_key(mock_rate_limiter: MagicMock, mock_logger: MagicMock) -> None:
    middleware = ThrottlingMiddleware(rate_limiter=mock_rate_limiter, logger=mock_logger)
    handler = AsyncMock()
    data: dict[str, object] = {"chat": ChatContext(tg_id=-1001, type=ChatType.SUPERGROUP)}

    await middleware(handler, MagicMock(), data)

    assert mock_rate_limiter.call.await_count == 2
    assert mock_rate_limiter.call.await_args_list[1].args[1] == ThrottlingMiddleware._rl_throttle_key(-1001)


@pytest.mark.unit
def test_throttle_key_format() -> None:
    assert ThrottlingMiddleware._rl_throttle_key(99) == "throttle:99"
    assert ThrottlingMiddleware._rl_throttle_key(-100) == "throttle:-100"
