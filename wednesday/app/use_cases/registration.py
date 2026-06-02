from app.dto import ChatContext, UserContext
from app.protocols import CacheRepoRegistry, Logger, UoW
from domain.chat import ChatProfile
from domain.user import UserProfile

from ..services import RegistrationService


class RegistrationUseCase:
    """
    Orchestrator for registration of update context:
    1) try to get user/chat from cache
    2) if miss -> go to DB through registration service
    3) after DB, put DTO in cache
    """

    def __init__(
        self,
        *,
        uow: UoW,
        reg_service: RegistrationService,
        cache_registry: CacheRepoRegistry,
        logger: Logger,
    ) -> None:
        self._uow = uow
        self._reg_service = reg_service
        self._cache_registry = cache_registry
        self._logger = logger.bind(module=self.__class__.__name__)

    async def reg_user(
        self,
        *,
        profile: UserProfile,
    ) -> UserContext:
        cache_repo = self._cache_registry.user
        cached = await cache_repo.get_by_id(profile.telegram_id)
        if cached is not None:
            self._logger.debug(
                "Registration cache hit",
                entity="user",
                tg_id=profile.telegram_id,
            )
            return cached

        self._logger.debug(
            "Registration cache miss, loading user",
            entity="user",
            tg_id=profile.telegram_id,
        )
        async with self._uow:
            resolved = await self._reg_service.get_or_create_user(profile=profile, repo=self._uow.users)

        await cache_repo.set(resolved)
        self._logger.debug(
            "Registration user context materialized",
            entity="user",
            tg_id=profile.telegram_id,
        )
        return UserContext.from_domain(resolved)

    async def find_user_by_tg_id(self, *, tg_id: int) -> UserContext | None:
        """Return existing user context; never creates a new aggregate."""
        cache_repo = self._cache_registry.user
        cached = await cache_repo.get_by_id(tg_id)
        if cached is not None:
            self._logger.debug("User lookup cache hit", tg_id=tg_id)
            return cached

        self._logger.debug("User lookup cache miss", tg_id=tg_id)
        async with self._uow:
            entity = await self._reg_service.get_user_if_exists(
                tg_id=tg_id,
                repo=self._uow.users,
            )
        if entity is None:
            return None

        await cache_repo.set(entity)
        return UserContext.from_domain(entity)

    async def reg_chat(
        self,
        *,
        profile: ChatProfile,
    ) -> ChatContext:
        cache_repo = self._cache_registry.chat
        cached = await cache_repo.get_by_id(profile.telegram_id)
        if cached is not None:
            self._logger.debug(
                "Registration cache hit",
                entity="chat",
                tg_id=profile.telegram_id,
            )
            return cached

        self._logger.debug(
            "Registration cache miss, loading chat",
            entity="chat",
            tg_id=profile.telegram_id,
        )
        async with self._uow:
            resolved = await self._reg_service.get_or_create_chat(profile=profile, repo=self._uow.chats)

        await cache_repo.set(resolved)
        self._logger.debug(
            "Registration chat context materialized",
            entity="chat",
            tg_id=profile.telegram_id,
        )
        return ChatContext.from_domain(resolved)

    async def find_chat_by_tg_id(self, *, tg_id: int) -> ChatContext | None:
        """Return existing chat context; never creates a new aggregate."""
        cache_repo = self._cache_registry.chat
        cached = await cache_repo.get_by_id(tg_id)
        if cached is not None:
            self._logger.debug("Chat lookup cache hit", tg_id=tg_id)
            return cached

        self._logger.debug("Chat lookup cache miss", tg_id=tg_id)
        async with self._uow:
            entity = await self._reg_service.get_chat_if_exists(
                tg_id=tg_id,
                repo=self._uow.chats,
            )
        if entity is None:
            return None

        await cache_repo.set(entity)
        return ChatContext.from_domain(entity)
