from builtins import BaseException

from aiogram.exceptions import (
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)

from app.exceptions import TooManyRequests, unwrap_exception


def is_telegram_retryable(exception: BaseException) -> bool:
    """
    Decides if the exception is retryable for Telegram API.
    """

    exception = unwrap_exception(exception)

    # 1️⃣ Network errors
    if isinstance(exception, TelegramNetworkError):
        return True

    # 2️⃣ Rate limit (TelegramRetryAfter contains retry_after)
    if isinstance(exception, TelegramRetryAfter):
        return True

    # 3️⃣ Internal Telegram errors (5xx)
    if isinstance(exception, TelegramServerError):
        return True

    # 4️⃣ Internal rate limit errors
    if isinstance(exception, TooManyRequests):
        return True

    return False
