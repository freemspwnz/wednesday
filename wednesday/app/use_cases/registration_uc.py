from __future__ import annotations

from app.dto import ChatContext, UserContext
from app.protocols import ICacheRepoRegistry, ILogger, IUoW

from ..services import RegistrationService


class RegistrationUseCase:
    """
    Оркестратор регистрации контекста update:
    1) пробуем взять user/chat из кэша
    2) если miss -> идем в БД через registration services
    3) после БД кладем DTO в кэш
    """

    def __init__(
        self,
        *,
        uow: IUoW,
        reg_service: RegistrationService,
        cache_registry: ICacheRepoRegistry,
        logger: ILogger,
    ) -> None:
        self._uow = uow
        self._reg_service = reg_service
        self._cache_registry = cache_registry
        self._logger = logger.bind(module=self.__class__.__name__)

    async def reg_user(
        self,
        *,
        dto: UserContext,
    ) -> UserContext:
        cache_repo = self._cache_registry.user
        cached = await cache_repo.get_by_id(dto.tg_id)
        if cached is not None:
            self._logger.debug(
                "Registration cache hit",
                entity="user",
                tg_id=dto.tg_id,
            )
            return cached

        self._logger.debug(
            "Registration cache miss, loading user",
            entity="user",
            tg_id=dto.tg_id,
        )
        async with self._uow:
            resolved = await self._reg_service.get_or_create_user(dto=dto, repo=self._uow.users)

        await cache_repo.set(resolved)
        self._logger.debug(
            "Registration user context materialized",
            entity="user",
            tg_id=dto.tg_id,
        )
        return UserContext.from_domain(resolved)

    async def reg_chat(
        self,
        *,
        dto: ChatContext,
    ) -> ChatContext:
        cache_repo = self._cache_registry.chat
        cached = await cache_repo.get_by_id(dto.tg_id)
        if cached is not None:
            self._logger.debug(
                "Registration cache hit",
                entity="chat",
                tg_id=dto.tg_id,
            )
            return cached

        self._logger.debug(
            "Registration cache miss, loading chat",
            entity="chat",
            tg_id=dto.tg_id,
        )
        async with self._uow:
            resolved = await self._reg_service.get_or_create_chat(dto=dto, repo=self._uow.chats)

        await cache_repo.set(resolved)
        self._logger.debug(
            "Registration chat context materialized",
            entity="chat",
            tg_id=dto.tg_id,
        )
        return ChatContext.from_domain(resolved)
