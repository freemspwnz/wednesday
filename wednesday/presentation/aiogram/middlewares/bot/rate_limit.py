from typing import TypeVar

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import Response, TelegramMethod

from app.exceptions import LimitStorageError, TooManyRequests
from app.protocols import Logger, RateLimiter

from ..utils import is_chat

T = TypeVar("T")


class RateLimitRequestMW(BaseRequestMiddleware):
    """Rate limiter middleware for outgoing Telegram API requests.

    On LimitStorageError, skips limits and proceeds (fail-open), same as inbound throttling.
    """

    def __init__(
        self,
        *,
        rate_limiter: RateLimiter,
        logger: Logger,
    ) -> None:
        self._limiter = rate_limiter
        self._limits = rate_limiter.limits
        self._logger = logger.bind(module=self.__class__.__name__)

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[T],
        bot: Bot,
        method: TelegramMethod[T],
    ) -> Response[T]:
        chat_id = getattr(method, "chat_id", None)
        key = "unknown"
        method_name = method.__class__.__name__

        try:
            limit = self._limits["global"]
            key = "global"
            await self._limiter.call(limit, key)

            if chat_id is not None:
                if is_chat(chat_id):
                    limit = self._limits["chat"]
                    key = self._rl_outbound_chat_key(chat_id)
                else:
                    limit = self._limits["user"]
                    key = self._rl_outbound_user_key(chat_id)

                await self._limiter.call(limit, key)

            return await make_request(bot, method)

        except TooManyRequests:
            self._logger.warning(
                "Rate limit exceeded",
                method=method_name,
                key=key,
            )
            raise

        except LimitStorageError:
            self._logger.warning(
                "Rate limit skipped: storage unavailable",
                method=method_name,
                key=key,
            )
            return await make_request(bot, method)

        except Exception:
            self._logger.exception(
                "Unexpected error while rate limiting",
                method=method_name,
                key=key,
            )
            raise

    @staticmethod
    def _rl_outbound_chat_key(chat_id: int | str) -> str:
        return f"group:{chat_id}"

    @staticmethod
    def _rl_outbound_user_key(user_id: int | str) -> str:
        return f"user:{user_id}"
