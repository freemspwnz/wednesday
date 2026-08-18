"""In-process catalog delivery for chat schedule slots."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.protocols import Logger, RequestScope, ScopeFactory
from domain.chat import Chat
from domain.kernel.vo import AwareDatetime

from ..routers.image.vote import build_vote_kb

_SlotKey = tuple[UUID, date, int, int]


class CatalogScheduleRunner:
    """Send unseen catalog photos when a chat schedule slot is due.

    Shares the bot process and Telegram session (outbound limits/retries).
    Does not call GigaChat. Duplicate sends in the same local minute are
    suppressed in-memory and reset on process restart.
    """

    def __init__(
        self,
        *,
        bot: Bot,
        scope_factory: ScopeFactory,
        logger: Logger,
    ) -> None:
        self._bot = bot
        self._scope_factory = scope_factory
        self._logger = logger.bind(module=self.__class__.__name__)
        self._fired: set[_SlotKey] = set()

    async def run(self) -> None:
        self._logger.info("Catalog schedule runner started")
        try:
            while True:
                await self.tick(at=AwareDatetime.now_utc())
                await asyncio.sleep(self._seconds_until_next_minute(datetime.now(UTC)))
        except asyncio.CancelledError:
            self._logger.info("Catalog schedule runner stopped")
            raise

    async def tick(self, *, at: AwareDatetime) -> None:
        self._prune_fired(at)
        try:
            async with self._scope_factory() as scope:
                due = await scope.chat_schedule_uc.list_due(at=at)
                for chat in due:
                    await self._deliver(scope=scope, chat=chat, at=at)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("Catalog schedule tick failed")

    async def _deliver(self, *, scope: RequestScope, chat: Chat, at: AwareDatetime) -> None:
        key = self._slot_key(chat, at)
        if key in self._fired:
            return

        try:
            card = await scope.image_catalog_uc.pick_for_chat(chat_id=chat.id, at=at)
            if card is None:
                self._logger.info(
                    "Catalog schedule skipped: no unseen image",
                    chat_id=str(chat.id.value),
                    tg_id=chat.profile.telegram_id,
                )
                self._fired.add(key)
                return

            await self._bot.send_photo(
                chat_id=chat.profile.telegram_id,
                photo=str(card.file_id),
                reply_markup=build_vote_kb(image_id=str(card.id), rating=card.rating),
            )
        except TelegramAPIError:
            self._logger.warning(
                "Catalog schedule send failed",
                chat_id=str(chat.id.value),
                tg_id=chat.profile.telegram_id,
                exc_info=True,
            )
            return
        except Exception:
            self._logger.warning(
                "Catalog schedule delivery failed",
                chat_id=str(chat.id.value),
                tg_id=chat.profile.telegram_id,
                exc_info=True,
            )
            return

        self._fired.add(key)
        self._logger.info(
            "Catalog schedule photo sent",
            chat_id=str(chat.id.value),
            tg_id=chat.profile.telegram_id,
            image_id=str(card.id.value),
        )

    def _prune_fired(self, at: AwareDatetime) -> None:
        cutoff = at.value.date() - timedelta(days=2)
        self._fired = {key for key in self._fired if key[1] >= cutoff}

    @staticmethod
    def _slot_key(chat: Chat, at: AwareDatetime) -> _SlotKey:
        local = at.value.astimezone(chat.schedules.timezone)
        return (chat.id.value, local.date(), local.hour, local.minute)

    @staticmethod
    def _seconds_until_next_minute(now: datetime) -> float:
        nxt = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        return max((nxt - now).total_seconds(), 0.0)
