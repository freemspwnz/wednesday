from functools import cached_property

from app.dto import ChatContext, UserContext
from app.protocols import CacheClient, CacheRepo, CacheRepoRegistry, Logger
from domain.chat import Chat
from domain.user import User

from .repos import RedisChatRepo, RedisUserRepo


class RedisRepoRegistry(CacheRepoRegistry):
    """Lazily constructs user/chat Redis cache repos over a shared ``CacheClient``."""

    def __init__(
        self,
        *,
        client: CacheClient,
        logger: Logger,
        key_prefix: str = "ctx",
    ) -> None:
        self._client = client
        self._logger = logger
        self._key_prefix = key_prefix

    @cached_property
    def user(self) -> CacheRepo[UserContext, User]:
        return RedisUserRepo(
            client=self._client,
            logger=self._logger,
            key_prefix=self._key_prefix,
        )

    @cached_property
    def chat(self) -> CacheRepo[ChatContext, Chat]:
        return RedisChatRepo(
            client=self._client,
            logger=self._logger,
            key_prefix=self._key_prefix,
        )
