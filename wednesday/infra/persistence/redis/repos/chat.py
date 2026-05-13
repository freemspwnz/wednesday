from datetime import timedelta

from pydantic import ValidationError

from app.dto import ChatContext
from app.protocols import CacheClient, CacheRepo, Logger
from domain.chat import Chat

from ..snapshots import CHAT_SNAPSHOT_VERSION, ChatSnapshot
from .utils import log_warning_and_invalidate_cache_key, raw_to_text, ttl_to_seconds


class RedisChatRepo(CacheRepo[ChatContext, Chat]):
    """Redis-backed cache for chat aggregates (snapshot JSON under a key prefix)."""

    def __init__(
        self,
        client: CacheClient,
        logger: Logger,
        ttl: int | timedelta = timedelta(minutes=10),
        key_prefix: str = "ctx",
    ) -> None:
        self._client = client
        self._ttl = ttl
        self._prefix = key_prefix
        self._logger = logger.bind(module=self.__class__.__name__)

    async def get_by_id(self, tg_id: int) -> ChatContext | None:
        key = self._key(tg_id)
        raw = await self._client.get(key)
        payload = raw_to_text(raw)
        if payload is None:
            return None

        try:
            snap = ChatSnapshot.model_validate_json(payload)
        except ValidationError:
            await log_warning_and_invalidate_cache_key(
                client=self._client,
                logger=self._logger,
                key=key,
                message="Invalid chat snapshot in cache",
            )
            return None
        except Exception:
            await log_warning_and_invalidate_cache_key(
                client=self._client,
                logger=self._logger,
                key=key,
                message="Failed to parse chat snapshot",
                exc_info=True,
            )
            return None

        if snap.v != CHAT_SNAPSHOT_VERSION:
            await log_warning_and_invalidate_cache_key(
                client=self._client,
                logger=self._logger,
                key=key,
                message="Stale chat snapshot version in cache",
            )
            return None
        return snap.to_context()

    async def set(self, chat: Chat, ttl: int | timedelta | None = None) -> None:
        key = self._key(chat.profile.telegram_id)
        expire = ttl_to_seconds(ttl) if ttl is not None else ttl_to_seconds(self._ttl)
        snap = ChatSnapshot.from_domain(chat)
        await self._client.set(key, snap.model_dump_json(), expire=expire)

    async def invalidate(self, tg_id: int) -> None:
        await self._client.delete(self._key(tg_id))

    def _key(self, tg_id: int) -> str:
        return f"{self._prefix}:chat:{tg_id}"
