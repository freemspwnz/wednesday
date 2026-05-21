"""Tests for bot session middleware (retry / rate limit)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage
from aiogram.methods.base import Response

from app.exceptions import AppError, LimitStorageError, MaxAttemptsExhaustedError, RetryError, TooManyRequests
from presentation.aiogram.middlewares.bot.rate_limit import RateLimitRequestMW
from presentation.aiogram.middlewares.bot.retry import RetryRequestMW


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limit_passes_request(mock_rate_limiter: MagicMock, mock_logger: MagicMock) -> None:
    middleware = RateLimitRequestMW(rate_limiter=mock_rate_limiter, logger=mock_logger)
    make_request = AsyncMock(return_value=Response(ok=True, result=True))
    method = SendMessage(chat_id=42, text="hi")

    await middleware(make_request, AsyncMock(spec=Bot), method)

    make_request.assert_awaited_once()
    assert mock_rate_limiter.call.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limit_raises_on_too_many_requests(
    mock_rate_limiter: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_rate_limiter.call.side_effect = TooManyRequests(retry_after=1, reset_at=0.0, limit="global")
    middleware = RateLimitRequestMW(rate_limiter=mock_rate_limiter, logger=mock_logger)

    with pytest.raises(TooManyRequests):
        await middleware(AsyncMock(), AsyncMock(spec=Bot), SendMessage(chat_id=1, text="x"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limit_fail_open_on_storage_error(
    mock_rate_limiter: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_rate_limiter.call.side_effect = LimitStorageError("down")
    middleware = RateLimitRequestMW(rate_limiter=mock_rate_limiter, logger=mock_logger)
    make_request = AsyncMock(return_value=Response(ok=True, result=True))

    await middleware(make_request, AsyncMock(spec=Bot), SendMessage(chat_id=1, text="x"))

    make_request.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limit_group_chat_key(mock_rate_limiter: MagicMock, mock_logger: MagicMock) -> None:
    middleware = RateLimitRequestMW(rate_limiter=mock_rate_limiter, logger=mock_logger)
    make_request = AsyncMock(return_value=Response(ok=True, result=True))

    await middleware(make_request, AsyncMock(spec=Bot), SendMessage(chat_id=-1001, text="hi"))

    assert mock_rate_limiter.call.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_delegates_to_retrier(mock_logger: MagicMock) -> None:
    retrier = MagicMock()
    expected = Response(ok=True, result=True)
    retrier.execute = AsyncMock(return_value=expected)
    middleware = RetryRequestMW(retrier=retrier, logger=mock_logger)
    make_request = AsyncMock()
    bot = AsyncMock(spec=Bot)
    method = SendMessage(chat_id=1, text="x")

    result = await middleware(make_request, bot, method)

    assert result == expected
    retrier.execute.assert_awaited_once_with(make_request, bot, method)


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc_type",
    [MaxAttemptsExhaustedError, RetryError, AppError, RuntimeError],
)
async def test_retry_logs_and_reraises(exc_type: type[Exception], mock_logger: MagicMock) -> None:
    retrier = MagicMock()
    if exc_type is MaxAttemptsExhaustedError:
        exc: Exception = MaxAttemptsExhaustedError(attempts=3)
    elif exc_type is RetryError:
        exc = RetryError("x")
    elif exc_type is AppError:
        exc = AppError("x")
    else:
        exc = RuntimeError("x")
    retrier.execute = AsyncMock(side_effect=exc)
    middleware = RetryRequestMW(retrier=retrier, logger=mock_logger)

    with pytest.raises(exc_type):
        await middleware(AsyncMock(), AsyncMock(spec=Bot), SendMessage(chat_id=1, text="x"))
