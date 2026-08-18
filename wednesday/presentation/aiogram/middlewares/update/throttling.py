"""Incoming update throttling middleware (Redis-backed)."""

import random
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, TelegramObject, Update

from app.exceptions import LimitStorageError, TooManyRequests
from app.protocols import Logger, RateLimiter

from ...messages import throttling as throttling_msg
from ..utils import is_chat


class ThrottlingMiddleware(BaseMiddleware):
    """Throttles incoming updates per chat/user via Redis.

    On LimitStorageError, proceeds without limits (fail-open), symmetric with outbound session rate limit.
    Callback flood is answered as a private toast; message flood may post a chat warning.
    """

    def __init__(
        self,
        *,
        limiter: RateLimiter,
        logger: Logger,
    ) -> None:
        self._limiter = limiter
        self._limits = limiter.limits
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
                callback = self._callback_from_event(event)
                if callback is not None:
                    warning = await self._maybe_warning_text(chat_id, throttling_msg.PERSONAL)
                    await self._answer_throttled_callback(callback, data, chat_id, text=warning)
                    return
                bot = data.get("bot")
                if isinstance(bot, Bot) and chat is not None:
                    warning = await self._maybe_warning_text(
                        chat_id,
                        throttling_msg.BY_CHAT_TYPE[chat.type],
                    )
                    if warning is not None:
                        await self._send_chat_warning(bot, chat_id, warning)
                return

        return await handler(event, data)

    async def _maybe_warning_text(self, chat_id: int, messages: Sequence[str]) -> str | None:
        try:
            await self._limiter.call(self._limits["throttling"], str(chat_id))
        except TooManyRequests:
            return None
        return random.choice(messages)

    async def _answer_throttled_callback(
        self,
        callback: CallbackQuery,
        data: dict[str, Any],
        chat_id: int,
        *,
        text: str | None,
    ) -> None:
        bot = data.get("bot")
        try:
            if isinstance(bot, Bot):
                await bot.answer_callback_query(callback_query_id=callback.id, text=text)
            else:
                await callback.answer(text)
        except Exception as answer_error:
            self._logger.warning(
                "Failed to answer throttled callback",
                chat_id=chat_id,
                error=str(answer_error),
            )

    async def _send_chat_warning(self, bot: Bot, chat_id: int, message: str) -> None:
        try:
            await bot.send_message(chat_id=chat_id, text=message)
        except Exception as send_error:
            self._logger.warning(
                "Failed to send throttle limit warning",
                chat_id=chat_id,
                error=str(send_error),
            )

    @staticmethod
    def _callback_from_event(event: TelegramObject) -> CallbackQuery | None:
        if isinstance(event, CallbackQuery):
            return event
        if isinstance(event, Update):
            return event.callback_query
        return None

    @staticmethod
    def _rl_throttle_key(chat_id: int | str) -> str:
        return f"throttle:{chat_id}"
