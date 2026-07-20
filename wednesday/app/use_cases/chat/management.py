from app.dto import ChatContext
from domain.chat import (
    Chat,
    ChatId,
    ChatManagementService,
    ChatProfile,
    ManagementActor,
)
from domain.kernel.vo import AwareDatetime

from .base import ChatBaseUseCase


class ChatManagementUseCase(ChatBaseUseCase):
    """Chat registration and management commands in a single UoW scope."""

    async def register(self, *, profile: ChatProfile) -> ChatContext:
        cached = await self._cache.get_by_id(profile.telegram_id)
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
            resolved = await ChatManagementService.get_or_create(
                profile=profile,
                repo=self._uow.chats,
                at=AwareDatetime.now_utc(),
            )

        await self._cache.set(resolved)
        self._logger.debug(
            "Registration chat context materialized",
            entity="chat",
            tg_id=profile.telegram_id,
        )
        return ChatContext.from_domain(resolved)

    async def find_by_tg_id(self, *, tg_id: int) -> ChatContext | None:
        """Return existing chat context; never creates a new aggregate."""
        cached = await self._cache.get_by_id(tg_id)
        if cached is not None:
            self._logger.debug("Chat lookup cache hit", tg_id=tg_id)
            return cached

        self._logger.debug("Chat lookup cache miss", tg_id=tg_id)
        async with self._uow:
            entity = await ChatManagementService.get_if_exists(
                tg_id=tg_id,
                repo=self._uow.chats,
            )
        if entity is None:
            return None

        await self._cache.set(entity)
        return ChatContext.from_domain(entity)

    async def change_profile(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        new_profile: ChatProfile,
        at: AwareDatetime,
    ) -> Chat:
        return await self._run_mutating(
            action="change_profile",
            chat_id=chat_id,
            runner=lambda: ChatManagementService.change_profile(
                id=chat_id,
                actor=actor,
                new_profile=new_profile,
                repo=self._uow.chats,
                at=at,
            ),
        )

    async def activate(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        return await self._run_mutating(
            action="activate",
            chat_id=chat_id,
            runner=lambda: ChatManagementService.activate(
                id=chat_id,
                actor=actor,
                repo=self._uow.chats,
                at=at,
            ),
        )

    async def deactivate(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        at: AwareDatetime,
    ) -> Chat:
        return await self._run_mutating(
            action="deactivate",
            chat_id=chat_id,
            runner=lambda: ChatManagementService.deactivate(
                id=chat_id,
                actor=actor,
                repo=self._uow.chats,
                at=at,
            ),
        )
