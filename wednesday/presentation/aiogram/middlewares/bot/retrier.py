from typing import TypeVar

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.methods import Response, TelegramMethod

from app.exceptions import AppError, MaxAttemptsExhaustedError, RetryError
from app.protocols import Logger, Retrier

T = TypeVar("T")


class RetryRequestMW(BaseRequestMiddleware):
    """Retry middleware for outgoing Telegram API requests."""

    def __init__(
        self,
        *,
        retrier: Retrier,
        logger: Logger,
    ) -> None:
        self._retrier = retrier
        self._logger = logger.bind(module=self.__class__.__name__)

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[T],
        bot: Bot,
        method: TelegramMethod[T],
    ) -> Response[T]:
        method_name = method.__class__.__name__
        try:
            return await self._retrier.execute(make_request, bot, method)
        except MaxAttemptsExhaustedError as exc:
            self._logger.warning(
                "Telegram API retries exhausted",
                method=method_name,
                error=str(exc),
            )
            raise
        except RetryError as exc:
            self._logger.warning(
                "Retry policy rejected request",
                method=method_name,
                error=str(exc),
            )
            raise
        except AppError as exc:
            self._logger.error(
                "AppError while retrying Telegram API call",
                method=method_name,
                error=str(exc),
            )
            raise
        except Exception as exc:
            self._logger.error(
                "Unexpected error while retrying Telegram API call",
                method=method_name,
                error=str(exc),
                exc_info=True,
            )
            raise
