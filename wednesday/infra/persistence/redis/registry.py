from functools import cached_property

from redis.asyncio import Redis

from app.dto import ChatContext, UserContext
from app.protocols import CacheClient, CacheMetrics, CacheRepo, CacheRepoRegistry, Logger
from domain.chat import Chat
from domain.user import User

from .client import RedisClient
from .repos import RedisChatRepo, RedisUserRepo


class RedisRepoRegistry(CacheRepoRegistry):
    """Lazily builds user/chat Redis cache repos over one shared ``RedisClient``.

    Owns client construction from the injected ``Redis`` connection, metrics, and logger.
    """

    def __init__(
        self,
        *,
        redis: Redis,
        key_prefix: str = "ctx",
        metrics: CacheMetrics,
        logger: Logger,
    ) -> None:
        self._redis = redis
        self._key_prefix = key_prefix
        self._metrics = metrics
        self._logger = logger

    @cached_property
    def users(self) -> CacheRepo[UserContext, User]:
        return RedisUserRepo(
            client=self._client,
            key_prefix=self._key_prefix,
            logger=self._logger,
        )

    @cached_property
    def chats(self) -> CacheRepo[ChatContext, Chat]:
        return RedisChatRepo(
            client=self._client,
            key_prefix=self._key_prefix,
            logger=self._logger,
        )

    @cached_property
    def _client(self) -> CacheClient:
        return RedisClient(
            redis=self._redis,
            metrics=self._metrics,
            logger=self._logger,
        )
