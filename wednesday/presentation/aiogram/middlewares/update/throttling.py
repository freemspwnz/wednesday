"""Incoming update throttling middleware (Redis-backed)."""

from __future__ import annotations

import random
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject

from app.exceptions import LimitStorageError, TooManyRequests
from app.protocols import Logger, RateLimiter

from ...messages import throttling as throttling_msg
from ..utils import is_chat


class ThrottlingMiddleware(BaseMiddleware):
    """Throttles incoming updates per chat/user via Redis.

    On LimitStorageError, proceeds without limits (fail-open), symmetric with outbound session rate limit.
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
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:  # noqa: ANN401
        chat = data.get("chat")
        chat_id = int(chat.tg_id) if chat is not None else None
        if chat_id is not None:
            try:
                await self._limiter.call(self._limits["global"], "global")
                if is_chat(chat_id):
                    await self._limiter.call(self._limits["chat"], self._rl_throttle_key(chat_id))
                else:
                    await self._limiter.call(self._limits["user"], self._rl_throttle_key(chat_id))

            except LimitStorageError:
                self._logger.warning(
                    "Throttling skipped: rate limiter storage unavailable",
                    chat_id=chat_id,
                )
                return await handler(event, data)

            except TooManyRequests:
                self._logger.warning("Throttling limit exceeded", chat_id=chat_id)
                bot = data.get("bot")
                if isinstance(bot, Bot) and chat is not None and chat_id is not None:
                    try:
                        await self._limiter.call(self._limits["throttling"], str(chat_id))
                    except TooManyRequests:
                        pass
                    else:
                        chat_type = chat.type
                        message = random.choice(throttling_msg.BY_CHAT_TYPE[chat_type])
                        try:
                            await bot.send_message(chat_id=chat_id, text=message)
                        except Exception as send_error:
                            self._logger.warning(
                                "Failed to send throttle limit warning",
                                chat_id=chat_id,
                                error=str(send_error),
                            )
                return

        return await handler(event, data)

    @staticmethod
    def _rl_throttle_key(chat_id: int | str) -> str:
        return f"throttle:{chat_id}"
