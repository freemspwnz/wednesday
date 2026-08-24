from builtins import BaseException

from aiogram.exceptions import (
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)

from app.exceptions import TooManyRequests, iter_exception_chain

_RETRYABLE = (
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TooManyRequests,
)


def is_telegram_retryable(exception: BaseException) -> bool:
    return any(isinstance(item, _RETRYABLE) for item in iter_exception_chain(exception))
