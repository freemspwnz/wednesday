"""Tests for bot session middleware (retry / rate limit)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramServerError
from aiogram.methods import SendMessage
from aiogram.methods.base import Response

from app.exceptions import AppError, LimitStorageError, MaxAttemptsExhaustedError, RetryError, TooManyRequests
from presentation.aiogram.middlewares.request.limiter import RateLimitRequestMW
from presentation.aiogram.middlewares.request.retrier import RetryRequestMW

_TELEGRAM_METHOD = MagicMock()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limit_passes_request(mock_limiter: MagicMock, mock_logger: MagicMock) -> None:
    middleware = RateLimitRequestMW(limiter=mock_limiter, logger=mock_logger)
    make_request = AsyncMock(return_value=Response(ok=True, result=True))
    method = SendMessage(chat_id=42, text="hi")

    await middleware(make_request, AsyncMock(spec=Bot), method)

    make_request.assert_awaited_once()
    assert mock_limiter.call.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limit_raises_on_too_many_requests(
    mock_limiter: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_limiter.call.side_effect = TooManyRequests(retry_after=1, reset_at=0.0, limit="global")
    middleware = RateLimitRequestMW(limiter=mock_limiter, logger=mock_logger)

    with pytest.raises(TooManyRequests):
        await middleware(AsyncMock(), AsyncMock(spec=Bot), SendMessage(chat_id=1, text="x"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limit_fail_open_on_storage_error(
    mock_limiter: MagicMock,
    mock_logger: MagicMock,
) -> None:
    mock_limiter.call.side_effect = LimitStorageError("down")
    middleware = RateLimitRequestMW(limiter=mock_limiter, logger=mock_logger)
    make_request = AsyncMock(return_value=Response(ok=True, result=True))

    await middleware(make_request, AsyncMock(spec=Bot), SendMessage(chat_id=1, text="x"))

    make_request.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limit_group_chat_key(mock_limiter: MagicMock, mock_logger: MagicMock) -> None:
    middleware = RateLimitRequestMW(limiter=mock_limiter, logger=mock_logger)
    make_request = AsyncMock(return_value=Response(ok=True, result=True))

    await middleware(make_request, AsyncMock(spec=Bot), SendMessage(chat_id=-1001, text="hi"))

    assert mock_limiter.call.await_count == 2


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

    if exc_type is MaxAttemptsExhaustedError:
        mock_logger.warning.assert_called_once()
        assert mock_logger.warning.call_args.args[0] == "Telegram API retries exhausted"
        mock_logger.error.assert_not_called()
    elif exc_type is RetryError:
        mock_logger.warning.assert_called_once()
        assert mock_logger.warning.call_args.args[0] == "Retry policy rejected request"
        mock_logger.error.assert_not_called()
    elif exc_type is AppError:
        mock_logger.error.assert_called_once()
        assert mock_logger.error.call_args.args[0] == "AppError while retrying Telegram API call"
        mock_logger.warning.assert_not_called()
    else:
        mock_logger.error.assert_called_once()
        assert mock_logger.error.call_args.args[0] == "Unexpected error while retrying Telegram API call"
        mock_logger.warning.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rate_limit_does_not_log_downstream_telegram_errors(
    mock_limiter: MagicMock,
    mock_logger: MagicMock,
) -> None:
    middleware = RateLimitRequestMW(limiter=mock_limiter, logger=mock_logger)
    make_request = AsyncMock(
        side_effect=TelegramNetworkError(method=_TELEGRAM_METHOD, message="Request timeout error"),
    )

    with pytest.raises(TelegramNetworkError):
        await middleware(make_request, AsyncMock(spec=Bot), SendMessage(chat_id=1, text="x"))

    mock_logger.exception.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc",
    [
        TelegramNetworkError(method=_TELEGRAM_METHOD, message="Request timeout error"),
        TelegramServerError(method=_TELEGRAM_METHOD, message="Bad Gateway"),
    ],
)
async def test_retry_reraises_telegram_transport_without_unexpected_log(
    exc: Exception,
    mock_logger: MagicMock,
) -> None:
    retrier = MagicMock()
    retrier.execute = AsyncMock(side_effect=exc)
    middleware = RetryRequestMW(retrier=retrier, logger=mock_logger)

    with pytest.raises(type(exc)):
        await middleware(AsyncMock(), AsyncMock(spec=Bot), SendMessage(chat_id=1, text="x"))

    mock_logger.error.assert_not_called()
    mock_logger.warning.assert_not_called()
