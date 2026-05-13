from datetime import timedelta

from pydantic import ValidationError

from app.dto import UserContext
from app.protocols import CacheClient, CacheRepo, Logger
from domain.user import User

from ..snapshots import USER_SNAPSHOT_VERSION, UserSnapshot
from .utils import log_warning_and_invalidate_cache_key, raw_to_text, ttl_to_seconds


class RedisUserRepo(CacheRepo[UserContext, User]):
    """Redis-backed cache for user aggregates (snapshot JSON under a key prefix)."""

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
            snap = UserSnapshot.model_validate_json(payload)
        except ValidationError:
            await log_warning_and_invalidate_cache_key(
                client=self._client,
                logger=self._logger,
                key=key,
                message="Invalid user snapshot in cache",
            )
            return None
        except Exception:
            await log_warning_and_invalidate_cache_key(
                client=self._client,
                logger=self._logger,
                key=key,
                message="Failed to parse user snapshot",
                exc_info=True,
            )
            return None

        if snap.v != USER_SNAPSHOT_VERSION:
            await log_warning_and_invalidate_cache_key(
                client=self._client,
                logger=self._logger,
                key=key,
                message="Stale user snapshot version in cache",
            )
            return None
        return snap.to_context()

    async def set(self, user: User, ttl: int | timedelta | None = None) -> None:
        key = self._key(user.profile.telegram_id)
        expire = ttl_to_seconds(ttl) if ttl is not None else ttl_to_seconds(self._ttl)
        snap = UserSnapshot.from_domain(user)
        await self._client.set(key, snap.model_dump_json(), expire=expire)

    async def invalidate(self, tg_id: int) -> None:
        await self._client.delete(self._key(tg_id))

    def _key(self, tg_id: int) -> str:
        return f"{self._prefix}:user:{tg_id}"
