from datetime import timedelta

from app.dto import UserContext
from app.exceptions import CacheInvalidDataError, CacheStaleDataError
from app.protocols import CacheClient, CacheRepo, Logger

from ..codec import dump_user_context, load_user_context
from .utils import log_warning_and_invalidate_cache_key, raw_to_text, ttl_to_seconds


class RedisUserRepo(CacheRepo[UserContext]):
    """Redis-backed cache for user contexts (JSON under a key prefix)."""

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

    async def get_by_id(self, tg_id: int) -> UserContext | None:
        key = self._key(tg_id)
        raw = await self._client.get(key)
        payload = raw_to_text(raw)
        if payload is None:
            return None

        try:
            context = load_user_context(payload)
        except CacheStaleDataError:
            await log_warning_and_invalidate_cache_key(
                client=self._client,
                logger=self._logger,
                key=key,
                message="Stale user context in cache",
            )
            return None
        except CacheInvalidDataError:
            await log_warning_and_invalidate_cache_key(
                client=self._client,
                logger=self._logger,
                key=key,
                message="Invalid user context in cache",
                exc_info=True,
            )
            return None

        return context

    async def set(self, context: UserContext, ttl: int | timedelta | None = None) -> None:
        key = self._key(context.tg_id)
        expire = ttl_to_seconds(ttl) if ttl is not None else ttl_to_seconds(self._ttl)
        payload = dump_user_context(context)
        await self._client.set(key, payload, expire=expire)

    async def invalidate(self, tg_id: int) -> None:
        await self._client.delete(self._key(tg_id))

    def _key(self, tg_id: int) -> str:
        return f"{self._prefix}:user:{tg_id}"
