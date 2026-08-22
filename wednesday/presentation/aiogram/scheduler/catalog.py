"""In-process catalog delivery for chat schedule slots."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.dto import ChatContext
from app.protocols import Logger, RequestScope, ScopeFactory

from ..messages import image as image_msg
from ..routers.image.vote import build_vote_kb


class CatalogScheduleRunner:
    """Send unseen catalog photos when a chat schedule slot is due.

    Shares the bot process and Telegram session (outbound limits/retries).
    Does not call GigaChat. A catalog view is recorded only after Telegram
    accepts the photo. If the chat has no unseen image, send a notice
    suggesting ``/generate`` — not a silent skip.

    Duplicate sends in the same local minute are suppressed in-memory and
    reset on process restart. A failed send also occupies that minute so
    the tick does not consume the next unseen image.
    """

    type _SlotKey = tuple[str, date, int, int]

    _fired: set[_SlotKey]

    def __init__(
        self,
        *,
        bot: Bot,
        scope: ScopeFactory,
        logger: Logger,
    ) -> None:
        self._bot = bot
        self._scope = scope
        self._logger = logger.bind(module=self.__class__.__name__)
        self._fired = set()

    async def run(self) -> None:
        self._logger.info("Catalog schedule runner started")
        try:
            while True:
                at = datetime.now(UTC)
                await self.tick(at=at)
                await asyncio.sleep(self._seconds_until_next_minute(at))
        except asyncio.CancelledError:
            self._logger.info("Catalog schedule runner stopped")
            raise

    async def tick(self, *, at: datetime) -> None:
        self._prune_fired(at)
        try:
            async with self._scope() as scope:
                due = await scope.chat_schedule_uc.list_due(at=at)
                for chat in due:
                    await self._deliver(scope=scope, chat=chat, at=at)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("Catalog schedule tick failed")

    async def _deliver(self, *, scope: RequestScope, chat: ChatContext, at: datetime) -> None:
        key = self._slot_key(chat, at)
        if key in self._fired:
            return

        try:
            card = await scope.image_catalog_uc.pick_for_chat(chat_id=chat.id)
        except Exception:
            self._logger.warning(
                "Catalog schedule pick failed",
                chat_id=chat.id,
                tg_id=chat.tg_id,
                exc_info=True,
            )
            return

        if card is None:
            await self._send_empty_notice(chat=chat, key=key)
            return

        try:
            await self._bot.send_photo(
                chat_id=chat.tg_id,
                photo=card.file_id,
                reply_markup=build_vote_kb(
                    image_id=card.id,
                    likes=card.likes,
                    dislikes=card.dislikes,
                ),
            )
        except TelegramAPIError:
            self._logger.warning(
                "Catalog schedule send failed",
                chat_id=chat.id,
                tg_id=chat.tg_id,
                exc_info=True,
            )
            self._fired.add(key)
            return
        except Exception:
            self._logger.warning(
                "Catalog schedule delivery failed",
                chat_id=chat.id,
                tg_id=chat.tg_id,
                exc_info=True,
            )
            self._fired.add(key)
            return

        try:
            await scope.image_catalog_uc.mark_shown(
                chat_id=chat.id,
                image_id=card.id,
                at=at,
            )
        except Exception:
            self._logger.warning(
                "Catalog schedule mark shown failed",
                chat_id=chat.id,
                tg_id=chat.tg_id,
                image_id=card.id,
                exc_info=True,
            )

        self._fired.add(key)
        self._logger.info(
            "Catalog schedule photo sent",
            chat_id=chat.id,
            tg_id=chat.tg_id,
            image_id=card.id,
        )

    async def _send_empty_notice(self, *, chat: ChatContext, key: _SlotKey) -> None:
        try:
            await self._bot.send_message(
                chat_id=chat.tg_id,
                text=image_msg.SCHEDULE_CATALOG_EMPTY,
            )
        except TelegramAPIError:
            self._logger.warning(
                "Catalog schedule notice failed",
                chat_id=chat.id,
                tg_id=chat.tg_id,
                exc_info=True,
            )
        else:
            self._logger.info(
                "Catalog schedule notice: no unseen image",
                chat_id=chat.id,
                tg_id=chat.tg_id,
            )
        self._fired.add(key)

    def _prune_fired(self, at: datetime) -> None:
        cutoff = at.date() - timedelta(days=2)
        self._fired = {key for key in self._fired if key[1] >= cutoff}

    @staticmethod
    def _slot_key(chat: ChatContext, at: datetime) -> _SlotKey:
        local = at.astimezone(ZoneInfo(chat.timezone))
        return (chat.id, local.date(), local.hour, local.minute)

    @staticmethod
    def _seconds_until_next_minute(now: datetime) -> float:
        nxt = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        return max((nxt - now).total_seconds(), 0.0)
