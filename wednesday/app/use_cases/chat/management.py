from zoneinfo import ZoneInfo

from app.dto import ChatContext
from domain.chat import (
    Chat,
    ChatId,
    ChatProfile,
    ChatScheduleSet,
    ManagementActor,
    Weekday,
)
from domain.chat.helpers import chat_id_from_tg
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
            resolved = await self._get_or_create(profile=profile, at=AwareDatetime.now_utc())

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
            entity = await self._uow.chats.get_by_id(chat_id_from_tg(tg_id))
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
            runner=lambda: self._change_profile(
                chat_id=chat_id,
                actor=actor,
                new_profile=new_profile,
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
            runner=lambda: self._activate(chat_id=chat_id, actor=actor, at=at),
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
            runner=lambda: self._deactivate(chat_id=chat_id, actor=actor, at=at),
        )

    async def _get_or_create(self, *, profile: ChatProfile, at: AwareDatetime) -> Chat:
        chat_id = chat_id_from_tg(profile.telegram_id)
        existing = await self._uow.chats.get_by_id(chat_id)
        if existing is not None:
            return existing

        schedules = ChatScheduleSet(
            timezone=ZoneInfo("UTC"),
            weekday=Weekday.WEDNESDAY,
            schedules=(),
        )
        chat = Chat.register(id=chat_id, profile=profile, schedules=schedules, at=at)
        await self._uow.chats.save(chat)
        self._logger.info("Chat registered", tg_id=profile.telegram_id)
        return chat

    async def _change_profile(
        self,
        *,
        chat_id: ChatId,
        actor: ManagementActor,
        new_profile: ChatProfile,
        at: AwareDatetime,
    ) -> Chat:
        chat = await self._load_chat_or_raise(chat_id=chat_id)
        chat.change_profile(actor=actor, new_profile=new_profile, at=at)
        await self._uow.chats.save(chat)
        return chat

    async def _activate(self, *, chat_id: ChatId, actor: ManagementActor, at: AwareDatetime) -> Chat:
        chat = await self._load_chat_or_raise(chat_id=chat_id)
        chat.activate(actor=actor, at=at)
        await self._uow.chats.save(chat)
        return chat

    async def _deactivate(self, *, chat_id: ChatId, actor: ManagementActor, at: AwareDatetime) -> Chat:
        chat = await self._load_chat_or_raise(chat_id=chat_id)
        chat.deactivate(actor=actor, at=at)
        await self._uow.chats.save(chat)
        return chat
