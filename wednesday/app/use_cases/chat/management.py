from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from app.dto import ChatContext
from domain.chat import (
    Chat,
    ChatId,
    ChatProfile,
    ChatScheduleSet,
    ChatType,
    ManagementActor,
    System,
    Weekday,
)
from domain.kernel import AwareDatetime, InvalidStateTransitionError

from .base import ChatBaseUseCase


class ChatManagementUseCase(ChatBaseUseCase):
    """Chat registration and management commands in a single UoW scope."""

    async def register(
        self,
        *,
        tg_id: int,
        type: str,
        title: str | None,
        username: str | None,
        at: datetime,
    ) -> ChatContext:
        time = AwareDatetime.from_datetime(at)
        cached = await self._cache.get_by_id(tg_id)
        if cached is not None:
            self._logger.debug(
                "Registration cache hit",
                entity="chat",
                tg_id=tg_id,
            )
            return cached

        self._logger.debug(
            "Registration cache miss, loading chat",
            entity="chat",
            tg_id=tg_id,
        )
        async with self._uow:
            resolved = await self._get_or_create(
                tg_id=tg_id,
                type=type,
                title=title,
                username=username,
                at=time,
            )

        ctx = ChatContext.from_domain(resolved)
        await self._cache.set(ctx)
        self._logger.debug(
            "Registration chat context materialized",
            entity="chat",
            tg_id=tg_id,
        )
        return ctx

    async def find_by_tg_id(self, *, tg_id: int) -> ChatContext | None:
        """Return existing chat context; never creates a new aggregate."""
        cached = await self._cache.get_by_id(tg_id)
        if cached is not None:
            self._logger.debug("Chat lookup cache hit", tg_id=tg_id)
            return cached

        self._logger.debug("Chat lookup cache miss", tg_id=tg_id)
        async with self._uow:
            chat = await self._uow.chats.get_by_id(ChatId.from_int(tg_id))
        if chat is None:
            return None

        ctx = ChatContext.from_domain(chat)
        await self._cache.set(ctx)
        return ctx

    async def activate(
        self,
        *,
        chat_id: str,
        actor_id: int,
        actor_role: str,
        at: datetime,
    ) -> ChatContext:
        return await self._run_mutating(
            action="activate",
            chat_id=chat_id,
            runner=lambda: self._activate(
                chat_id=ChatId(UUID(chat_id)),
                actor=self._actor(actor_id, actor_role, chat_id),
                at=AwareDatetime.from_datetime(at),
            ),
        )

    async def deactivate(
        self,
        *,
        chat_id: str,
        actor_id: int,
        actor_role: str,
        at: datetime,
    ) -> ChatContext:
        return await self._run_mutating(
            action="deactivate",
            chat_id=chat_id,
            runner=lambda: self._deactivate(
                chat_id=ChatId(UUID(chat_id)),
                actor=self._actor(actor_id, actor_role, chat_id),
                at=AwareDatetime.from_datetime(at),
            ),
        )

    async def on_bot_kicked(
        self,
        *,
        tg_id: int,
        at: datetime,
    ) -> ChatContext | None:
        """Bot removed from chat: pause broadcast if chat exists.

        Idempotent: missing chat or already inactive → None / current ctx, no error.
        """
        chat = await self.find_by_tg_id(tg_id=tg_id)
        if chat is None:
            return None

        try:
            return await self._run_mutating(
                action="on_bot_kicked",
                chat_id=chat.id,
                runner=lambda: self._deactivate(
                    chat_id=ChatId(UUID(chat.id)),
                    actor=System(),
                    at=AwareDatetime.from_datetime(at),
                ),
            )
        except InvalidStateTransitionError:
            self._logger.debug("Chat already inactive on bot leave", tg_id=tg_id)
            return chat

    async def _get_or_create(
        self,
        *,
        tg_id: int,
        type: str,
        title: str | None,
        username: str | None,
        at: AwareDatetime,
    ) -> Chat:
        chat_id = ChatId.from_int(tg_id)
        existing = await self._uow.chats.get_by_id(chat_id)
        if existing is not None:
            return existing

        profile = ChatProfile(
            type=ChatType(type),
            telegram_id=tg_id,
            title=title,
            username=username,
        )
        schedules = ChatScheduleSet(
            timezone=ZoneInfo("UTC"),
            weekday=Weekday.WEDNESDAY,
            schedules=(),
        )
        chat = Chat.register(id=chat_id, profile=profile, schedules=schedules, at=at)
        await self._uow.chats.save(chat)
        self._logger.info("Chat registered", tg_id=tg_id)
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
